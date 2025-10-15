"""Defines Identifier Provisioning."""

import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, TextIO

from configs.ingest_configs import ErrorLogTemplate
from dates.form_dates import (
    DATE_FORMATS,
    DEFAULT_DATE_FORMAT,
    DateFormatException,
    parse_date,
)
from enrollment.enrollment_project import EnrollmentProject, TransferInfo
from enrollment.enrollment_transfer import (
    CenterValidator,
    Demographics,
    EnrollmentRecord,
    NewGUIDRowValidator,
    NewPTIDRowValidator,
    TransferRecord,
    guid_available,
    has_known_naccid,
    is_new_enrollment,
    previously_enrolled,
)
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import CenterIdentifiers, IdentifierObject
from inputs.csv_reader import AggregateRowValidator, CSVVisitor, read_csv
from keys.keys import DefaultValues
from nacc_common.error_models import CSVLocation, FileError, FileErrorList, VisitKeys
from nacc_common.field_names import FieldNames
from notifications.email import EmailClient, create_ses_client
from outputs.error_logger import update_error_log_and_qc_metadata
from outputs.error_writer import ErrorWriter, ListErrorWriter
from outputs.errors import (
    empty_field_error,
    existing_participant_error,
    identifier_error,
    missing_field_error,
    partially_failed_file_error,
    system_error,
    unexpected_value_error,
)
from pydantic import ValidationError
from uploads.upload_error import UploaderError

log = logging.getLogger(__name__)


def update_record_level_error_log(
    *,
    input_record: Dict[str, Any],
    qc_passed: bool,
    project: ProjectAdaptor,
    gear_name: str,
    errors: FileErrorList,
    errorlog_template: Optional[ErrorLogTemplate] = None,
    transfer: Optional[bool] = False,
):
    """Update error log file for the visit and store error metadata in
    file.info.qc.

    Args:
        input_record: input record details
        qc_passed: whether the visit passed QC checks
        project: Flywheel project adaptor
        gear_name: gear that generated errors
        errors: list of error objects, expected to be JSON dicts
        errorlog_template (optional): error log naming template for module
        transfer (optional): is this a transfer request, default False

    Returns:
        bool: True if error log updated successfully, else False
    """

    if not errorlog_template:
        errorlog_template = ErrorLogTemplate(
            id_field=FieldNames.PTID, date_field=FieldNames.ENRLFRM_DATE
        )

    error_log_name = errorlog_template.instantiate(
        module=DefaultValues.ENROLLMENT_MODULE, record=input_record
    )

    status = "PASS" if qc_passed else "FAIL"
    if transfer and qc_passed:
        status = "IN REVIEW"

    if not error_log_name or not update_error_log_and_qc_metadata(
        error_log_name=error_log_name,
        destination_prj=project,
        gear_name=gear_name,
        state=status,
        errors=errors,
    ):
        raise GearExecutionError(
            "Failed to update error log for visit "
            f"{input_record[FieldNames.PTID]}, "
            f"{input_record[FieldNames.ENRLFRM_DATE]}"
        )


class EnrollmentBatch:
    """Collects new Identifier objects for committing to repository."""

    def __init__(self) -> None:
        self.__records: Dict[str, EnrollmentRecord] = {}

    def __iter__(self) -> Iterator[EnrollmentRecord]:
        """Returns an iterator to the the enrollment records in this batch."""
        return iter(self.__records.values())

    def __len__(self) -> int:
        """Returns the number of enrollment records in this batch."""
        return len(self.__records.values())

    def add(self, enrollment_record: EnrollmentRecord) -> None:
        """Adds the enrollment object to this batch.

        Args:
          enrollment_record: the enrollment object
        """
        identifier = enrollment_record.center_identifier
        self.__records[identifier.ptid] = enrollment_record

    def commit(self, repo: IdentifierRepository) -> None:
        """Adds participants to the repository.

        NACCIDs are added to records after identifiers are created.

        Args:
          repo: the repository for identifiers
        """
        if not self.__records:
            log.warning("No enrollment records found to create")
            return

        query = [record.query_object() for record in self.__records.values()]
        identifiers = repo.create_list(query)
        log.info("created %s new NACCIDs", len(identifiers))
        if len(query) != len(identifiers):
            log.warning("expected %s new IDs, got %s", len(query), len(identifiers))

        for identifier in identifiers:
            record = self.__records.get(identifier.ptid)
            if record:
                record.naccid = identifier.naccid


class TransferVisitor(CSVVisitor):
    """Visitor for processing transfers into a center."""

    def __init__(
        self,
        error_writer: ErrorWriter,
        transfer_info: TransferInfo,
        repo: IdentifierRepository,
        submitter: str,
    ) -> None:
        self.__error_writer = error_writer
        self.__transfer_info = transfer_info
        self.__repo = repo
        self.__submitter = submitter
        self.__naccid_identifier: Optional[IdentifierObject] = None
        self.__naccid: Optional[str] = None

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has expected column headings.

        Args:
          header: the list of column headings for file
        Returns:
          True if the header has expected columns, False otherwise.
        """
        expected_columns = {
            FieldNames.OLDADCID,
            FieldNames.OLDPTID,
            FieldNames.NACCIDKWN,
            FieldNames.NACCID,
            FieldNames.PREVENRL,
        }
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_field_error(expected_columns))
            return False

        return True

    def __naccid_visit(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits a row to process a known NACCID to gather existing
        identifiers.

        Identifiers are saved in visitor to match with identifiers for other
        form information.

        Args:
          row: the dictionary for the input row
          line_num: the line number of the row

        Returns:
          True if the rows has no expected NACCID, or the NACCID in the row
          exists. False otherwise.
        """
        if not has_known_naccid(row):
            return True

        self.__naccid = row.get(FieldNames.NACCID)
        if not self.__naccid:
            self.__error_writer.write(
                empty_field_error(
                    field=FieldNames.NACCID,
                    line=line_num,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=FieldNames.ENRLFRM_DATE
                    ),
                )
            )
            return False

        try:
            self.__naccid_identifier = self.__repo.get(naccid=self.__naccid)

            if self.__naccid_identifier:
                return True

            message = f"Did not find an active participant for NACCID {self.__naccid}"
        except (IdentifierRepositoryError, TypeError) as error:
            message = f"Error in looking up NACCID {self.__naccid}: {error}"

        self.__error_writer.write(
            identifier_error(
                field=FieldNames.NACCID,
                value=self.__naccid,
                line=line_num,
                message=message,
                visit_keys=VisitKeys.create_from(
                    record=row, date_field=FieldNames.ENRLFRM_DATE
                ),
            )
        )

        return False

    def __match_naccid(
        self, identifier: IdentifierObject, source: str, line_num: int
    ) -> bool:
        """Checks whether the identifier matches the NACCID in the visitor.

        Args:
          identifier: the identifier to match
          source: string describing columns for NACCID lookup
          line_num: the line number

        Returns:
          True if the identifier matches the NACCID. False, otherwise.
        """
        if not self.__naccid_identifier:
            return True

        if identifier.naccid == self.__naccid_identifier.naccid:
            return True

        self.__error_writer.write(
            FileError(
                error_type="error",  # pyright: ignore[reportCallIssue]
                error_code="mismatched-id",  # pyright: ignore[reportCallIssue]
                location=CSVLocation(line=line_num, column_name=source),
                message=(
                    "Different NACCIDs found for the input data in this form: "
                    f"{identifier.naccid}, {self.__naccid_identifier.naccid}"
                ),
            )
        )
        return False

    def __guid_visit(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits the row for an available GUID to gather existing identifiers.

        Checks whether identifiers match those already found.

        Args:
          row: the dictionary for the input row
          line_num: the line number of the row
        Returns:
          True if either the row does not have an expected GUID, or the GUID
          exists and is for same participant as other identifiers.
          False otherwise.
        """
        if not guid_available(row):
            return True

        guid = row[FieldNames.GUID]
        try:
            guid_identifier = self.__repo.get(guid=guid)
        except (IdentifierRepositoryError, TypeError) as error:
            self.__error_writer.write(
                identifier_error(
                    field=FieldNames.GUID,
                    value=guid,
                    line=line_num,
                    message=f"Error in looking up Identifier for GUID {guid}: {error}",
                )
            )
            return False

        if not guid_identifier:
            # It's possible for centers to generate different GUIDs for same participant
            log.warning(f"No active Identifier found for GUID {guid}")
            return True

        if not self.__match_naccid(guid_identifier, FieldNames.GUID, line_num):
            # Active participant exists with same GUID and a different NACCID
            return False

        self.__naccid_identifier = guid_identifier

        return True

    def __prevenrl_visit(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits the row for a previous enrollment to gather identifiers.

        Checks that identifiers match those already found.

        Args:
          row: the dictionary for the input row
          line_num: the line number of the row
        Returns:
          True if either the row does not indicate a previous enrollment, or
          the provided identifiers correspond to the same participant as other
          identifiers. False otherwise.
        """
        if not previously_enrolled(row):
            return True

        previous_adcid = row.get(FieldNames.OLDADCID)
        if previous_adcid is None:
            self.__error_writer.write(
                empty_field_error(
                    field=FieldNames.OLDADCID,
                    line=line_num,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=FieldNames.ENRLFRM_DATE
                    ),
                )
            )
            return False

        previous_ptid = row.get(FieldNames.OLDPTID)
        if not previous_ptid:  # OLDPTID is not a required field in the form
            return True

        try:
            ptid_identifier = self.__repo.get(adcid=previous_adcid, ptid=previous_ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            self.__error_writer.write(
                identifier_error(
                    value=previous_ptid,
                    line=line_num,
                    message=(
                        f"Error in looking up NACCID for OLDADCID {previous_adcid}, "
                        f"OLDPTID {previous_ptid}: {error}"
                    ),
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=FieldNames.ENRLFRM_DATE
                    ),
                )
            )
            return False

        if not ptid_identifier:
            self.__error_writer.write(
                identifier_error(
                    value=previous_ptid,
                    line=line_num,
                    message=(
                        f"No NACCID found for OLDADCID {previous_adcid}, "
                        f"OLDPTID {previous_ptid}"
                    ),
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=FieldNames.ENRLFRM_DATE
                    ),
                )
            )
            return False

        if not self.__match_naccid(
            ptid_identifier, f"{FieldNames.OLDADCID}-{FieldNames.OLDPTID}", line_num
        ):
            return False

        self.__naccid_identifier = ptid_identifier

        return True

    def __check_adcid_ptid(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that ADCID, PTID does not already correspond to an active
        NACCID.

        Args:
          row: the dictionary for the row

        Returns:
          True if no active NACCID is found for the ADCID, PTID, False otherwise
        """

        ptid = row["ptid"]
        adcid = row["adcid"]

        try:
            identifier = self.__repo.get(adcid=adcid, ptid=ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            self.__error_writer.write(
                identifier_error(
                    field=FieldNames.PTID,
                    value=ptid,
                    line=line_number,
                    message=(
                        "Error in looking up Identifier for "
                        f"ADCID {adcid}, PTID {ptid}: {error}"
                    ),
                )
            )
            return False

        if not identifier:
            return True

        if identifier.active:
            log.info(
                "Found active participant for (%s, %s): %s",
                adcid,
                ptid,
                identifier.naccid,
            )
            self.__error_writer.write(
                existing_participant_error(
                    field=FieldNames.PTID, line=line_number, value=ptid
                )
            )
            return False

        if not self.__match_naccid(
            identifier, f"{FieldNames.ADCID}-{FieldNames.PTID}", line_number
        ):
            return False

        self.__naccid_identifier = identifier

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits enrollment/transfer data for single form.

        Args:
          row: the dictionary for the row in the file
          line_num: the line number of the row
        Returns:
          True if the row is a valid transfer. False, otherwise.
        """
        if not self.__naccid_visit(row=row, line_num=line_num):
            return False

        if not self.__guid_visit(row=row, line_num=line_num):
            return False

        if not self.__prevenrl_visit(row=row, line_num=line_num):
            return False

        if not self.__check_adcid_ptid(row=row, line_number=line_num):
            return False

        try:
            enroll_date = parse_date(
                date_string=row[FieldNames.ENRLFRM_DATE], formats=DATE_FORMATS
            )
        except DateFormatException:
            self.__error_writer.write(
                unexpected_value_error(
                    field=FieldNames.ENRLFRM_DATE,
                    value=row[FieldNames.ENRLFRM_DATE],
                    expected="",
                    message="Expected valid datetime date",
                    line=line_num,
                )
            )
            return False

        new_identifiers = CenterIdentifiers(
            adcid=row[FieldNames.ADCID], ptid=row[FieldNames.PTID]
        )

        oldptid = row.get(FieldNames.OLDPTID)
        if oldptid is None or not str(oldptid).strip():
            oldptid = "unknown"

        self.__transfer_info.add(
            TransferRecord(
                status="pending",
                request_date=enroll_date,
                updated_date=datetime.now(),
                submitter=self.__submitter,
                center_identifiers=new_identifiers,
                initials=row.get(FieldNames.ENRLFRM_INITL),
                previous_adcid=row[FieldNames.OLDADCID],
                previous_ptid=oldptid,
                naccid=self.__naccid_identifier.naccid
                if self.__naccid_identifier
                else None,
                guid=row.get(FieldNames.GUID),
                demographics=Demographics.create_from(row=row),
            )
        )

        log.info("Participant transfer found on line %s", line_num)

        return True


class NewEnrollmentVisitor(CSVVisitor):
    """A CSV Visitor class for processing new enrollment forms."""

    def __init__(
        self,
        error_writer: ErrorWriter,
        repo: IdentifierRepository,
        batch: EnrollmentBatch,
    ) -> None:
        self.__batch = batch
        self.__validator = AggregateRowValidator(
            [
                NewPTIDRowValidator(repo, error_writer),
                NewGUIDRowValidator(repo, error_writer),
            ]
        )
        self.__error_writer = error_writer

    def visit_header(self, header: List[str]) -> bool:
        """Checks for ID columns in the header.

        Args:
          header: the list of header column names
        Returns:
          True if the header has expected columns. False, otherwise.
        """
        expected_columns = {FieldNames.GUID}
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_field_error(expected_columns))
            return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Adds an enrollment record to the batch for creating new identifiers.

        Args:
          row: the dictionary for the row
          line_num: the line number for the row
        Returns:
          True if the row is a valid enrollment. False, otherwise.
        """
        if not self.__validator.check(row, line_num):
            return False

        log.info(
            "Adding new enrollment for (%s,%s)",
            row[FieldNames.ADCID],
            row[FieldNames.PTID],
        )
        try:
            enroll_date = parse_date(
                date_string=row[FieldNames.ENRLFRM_DATE], formats=DATE_FORMATS
            )
        except DateFormatException:
            self.__error_writer.write(
                unexpected_value_error(
                    field=FieldNames.ENRLFRM_DATE,
                    value=row[FieldNames.ENRLFRM_DATE],
                    expected="",
                    message="Expected valid datetime date",
                    line=line_num,
                )
            )
            return False

        try:
            self.__batch.add(
                EnrollmentRecord(
                    center_identifier=CenterIdentifiers(
                        adcid=row[FieldNames.ADCID], ptid=row[FieldNames.PTID]
                    ),
                    guid=row.get(FieldNames.GUID) if row.get(FieldNames.GUID) else None,
                    naccid=None,
                    start_date=enroll_date,
                )
            )
            return True
        except ValidationError as validation_error:
            for error in validation_error.errors():
                if error["type"] == "string_pattern_mismatch":
                    field_name = str(error["loc"][0])
                    context = error.get("ctx", {"pattern": ""})
                    self.__error_writer.write(
                        unexpected_value_error(
                            field=field_name,
                            value=error["input"],
                            expected=context["pattern"],
                            message=f"Invalid {field_name.upper()}",
                            line=line_num,
                            visit_keys=VisitKeys.create_from(
                                record=row, date_field=FieldNames.ENRLFRM_DATE
                            ),
                        )
                    )

            return False


class ProvisioningVisitor(CSVVisitor):
    """A CSV Visitor class for processing participant enrollment and transfer
    forms."""

    def __init__(
        self,
        *,
        center_id: int,
        error_writer: ListErrorWriter,
        transfer_info: TransferInfo,
        batch: EnrollmentBatch,
        repo: IdentifierRepository,
        gear_name: str,
        project: ProjectAdaptor,
        submitter: str,
    ) -> None:
        self.__error_writer = error_writer
        self.__project = project
        self.__gear_name = gear_name
        self.__enrollment_visitor = NewEnrollmentVisitor(
            error_writer, repo=repo, batch=batch
        )
        self.__transfer_in_visitor = TransferVisitor(
            error_writer, repo=repo, submitter=submitter, transfer_info=transfer_info
        )
        self.__validator = CenterValidator(
            center_id=center_id,
            date_field=FieldNames.ENRLFRM_DATE,
            error_writer=error_writer,
        )

    def visit_header(self, header: List[str]) -> bool:
        """Prepares visitor to work with CSV file with given header.

        Args:
          header: the list of header names
        Returns:
          True if all of the visitors return True. False otherwise
        """
        expected_columns = {
            FieldNames.PTID,
            FieldNames.ADCID,
            FieldNames.ENRLFRM_DATE,
            FieldNames.ENRLTYPE,
        }
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_field_error(expected_columns))
            return False

        return self.__enrollment_visitor.visit_header(
            header
        ) and self.__transfer_in_visitor.visit_header(header)

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Provisions a NACCID for the ADCID and PTID.

        If form is
        - a new enrollment, then applies the NewEnrollmentVisitor.
        - a transfer TransferVisitor.

        Args:
          row: the dictionary for the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if the row is a valid enrollment or transfer.  False, otherwise.
        """

        # processing a new row, clear previous errors if any
        self.__error_writer.clear()

        if not self.__validator.check(row=row, line_number=line_num):
            update_record_level_error_log(
                input_record=row,
                qc_passed=False,
                project=self.__project,
                gear_name=self.__gear_name,
                errors=self.__error_writer.errors(),
            )
            return False

        if is_new_enrollment(row):
            try:
                success = self.__enrollment_visitor.visit_row(
                    row=row, line_num=line_num
                )
                if not success:  # Only update record level log if validation failed
                    update_record_level_error_log(
                        input_record=row,
                        qc_passed=False,
                        project=self.__project,
                        gear_name=self.__gear_name,
                        errors=self.__error_writer.errors(),
                    )
                return success
            except IdentifierRepositoryError as error:
                message = (
                    "Failed to assign a NACCID for PTID "
                    f"{row[FieldNames.PTID]}: {error}"
                )
                log.error(message)
                self.__error_writer.write(
                    identifier_error(
                        message=message,
                        field=FieldNames.PTID,
                        value=row[FieldNames.PTID],
                        line=line_num,
                        visit_keys=VisitKeys.create_from(
                            record=row, date_field=FieldNames.ENRLFRM_DATE
                        ),
                    )
                )
                update_record_level_error_log(
                    input_record=row,
                    qc_passed=False,
                    project=self.__project,
                    gear_name=self.__gear_name,
                    errors=self.__error_writer.errors(),
                )
                return False

        success = self.__transfer_in_visitor.visit_row(row=row, line_num=line_num)

        # Update visit level log for the transfer request
        update_record_level_error_log(
            input_record=row,
            qc_passed=success,
            project=self.__project,
            gear_name=self.__gear_name,
            errors=self.__error_writer.errors(),
            transfer=True,
        )

        return success


def send_email(
    sender_email: str,
    target_emails: List[str],
    group_lbl: str,
    project_lbl: str,
    transfer_ptids: List[str],
) -> None:
    """Send a raw email notifying target emails of the transfer request(s).

    Args:
        sender_email: The sender email
        target_emails: The target email(s)
        group_lbl: Flywheel group label
        project_lbl: Flywheel project label
        transfer_ptids: PTIDs pending for transfer
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    subject = f"Participant Transfer Request for {group_lbl}/{project_lbl}"
    body = (
        "\n\nParticipant transfer request(s) submitted for PTIDs "
        f"{transfer_ptids} in enrollment project {group_lbl}/{project_lbl}.\n"
        "Please review the details in project Information tab under transfers.\n\n"
    )

    client.send_raw(destinations=target_emails, subject=subject, body=body)


def run(
    *,
    input_file: TextIO,
    center_id: int,
    repo: IdentifierRepository,
    enrollment_project: EnrollmentProject,
    error_writer: ListErrorWriter,
    gear_name: str,
    submitter: str,
    sender_email: str,
    target_emails: List[str],
):
    """Runs identifier provisioning process.

    Args:
      input_file: the data input stream
      center_id: the ADCID for the center
      repo: the identifier repository
      enrollment_project: the project tracking enrollment
      error_writer: the error output writer
      gear_name: gear name
      submitter: User/Job uploaded the CSV file
      sender_email: The source email to send transfer request notification
      target_emails: The target email(s) that the notification to be delivered
    """
    transfer_info = TransferInfo(transfers={})
    enrollment_batch = EnrollmentBatch()
    try:
        success = read_csv(
            input_file=input_file,
            error_writer=error_writer,
            visitor=ProvisioningVisitor(
                center_id=center_id,
                batch=enrollment_batch,
                repo=repo,
                error_writer=error_writer,
                transfer_info=transfer_info,
                gear_name=gear_name,
                project=enrollment_project,
                submitter=submitter,
            ),
            clear_errors=True,
        )

        if not success:
            log.warning(
                "Some records in the input file failed validation. "
                "Check record level QC status."
            )

        log.info(
            "Requesting new NACCIDs for %s successfully validated records",
            len(enrollment_batch),
        )
        enrollment_batch.commit(repo)
    except (IdentifierRepositoryError, ValidationError) as error:
        raise GearExecutionError(error) from error

    for record in enrollment_batch:
        error_writer.clear()
        record_info = {
            FieldNames.PTID: record.center_identifier.ptid,
            FieldNames.ENRLFRM_DATE: record.start_date.strftime(DEFAULT_DATE_FORMAT),
        }
        if not record.naccid:
            message = (
                "Failed to generate NACCID for enrollment record "
                f"{record.center_identifier.adcid},"
                f"{record.center_identifier.ptid}"
            )
            log.error(message)
            error_writer.write(
                system_error(
                    message=message,
                    visit_keys=VisitKeys(
                        ptid=record_info[FieldNames.PTID],
                        date=record_info[FieldNames.ENRLFRM_DATE],
                    ),
                )
            )
            update_record_level_error_log(
                input_record=record_info,
                qc_passed=False,
                project=enrollment_project,
                gear_name=gear_name,
                errors=error_writer.errors(),
            )

            success = False
            continue

        if enrollment_project.find_subject(label=record.naccid):
            message = f"Subject with NACCID {record.naccid} exists"
            log.error(message)
            error_writer.write(
                system_error(
                    message=message,
                    visit_keys=VisitKeys(
                        ptid=record_info[FieldNames.PTID],
                        date=record_info[FieldNames.ENRLFRM_DATE],
                        naccid=record.naccid,
                    ),
                )
            )
            update_record_level_error_log(
                input_record=record_info,
                qc_passed=False,
                project=enrollment_project,
                gear_name=gear_name,
                errors=error_writer.errors(),
            )
            success = False
            continue

        try:
            log.info(
                f"Adding new subject {record.naccid} to enrollment project "
                f"{enrollment_project.group}/{enrollment_project.label}"
            )
            subject = enrollment_project.add_subject(record.naccid)
            subject.add_enrollment(record)
            # subject.update_demographics_info(demographics)
        except UploaderError as error:
            success = False
            message = f"Failed to create enrollment record for {record.naccid}: {error}"
            log.error(message)
            error_writer.write(
                system_error(
                    message=message,
                    visit_keys=VisitKeys(
                        ptid=record_info[FieldNames.PTID],
                        date=record_info[FieldNames.ENRLFRM_DATE],
                        naccid=record.naccid,
                    ),
                )
            )

        update_record_level_error_log(
            input_record=record_info,
            qc_passed=not error_writer.has_errors(),
            project=enrollment_project,
            gear_name=gear_name,
            errors=error_writer.errors(),
        )

    if len(transfer_info.transfers) > 0:
        enrollment_project.add_or_update_transfers(transfer_info)
        send_email(
            sender_email=sender_email,
            target_emails=target_emails,
            group_lbl=enrollment_project.group,
            project_lbl=enrollment_project.label,
            transfer_ptids=list(transfer_info.transfers.keys()),
        )

    if not success:
        error_writer.clear()
        error_writer.write(partially_failed_file_error())

    return success
