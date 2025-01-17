"""Defines Identifier Provisioning."""

import logging
from typing import Any, Dict, Iterator, List, Optional, TextIO

from dates.form_dates import DATE_FORMATS, DateFormatException, parse_date
from enrollment.enrollment_project import EnrollmentProject, TransferInfo
from enrollment.enrollment_transfer import (
    CenterValidator,
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
from keys.keys import DefaultValues, FieldNames
from outputs.errors import (
    CSVLocation,
    FileError,
    ListErrorWriter,
    empty_field_error,
    get_error_log_name,
    identifier_error,
    missing_field_error,
    partially_failed_file_error,
    system_error,
    unexpected_value_error,
    update_error_log_and_qc_metadata,
)
from pydantic import ValidationError

log = logging.getLogger(__name__)


def update_record_level_error_log(*,
                                  input_record: Dict[str, Any],
                                  qc_passed: bool,
                                  project: ProjectAdaptor,
                                  gear_name: str,
                                  errors: List[Dict[str, Any]],
                                  naming_template: Optional[Dict[str,
                                                                 str]] = None):
    """Update error log file for the visit and store error metadata in
    file.info.qc.

    Args:
        input_record: input record details
        qc_passed: whether the visit passed QC checks
        project: Flywheel project adaptor
        gear_name: gear that generated errors
        errors: list of error objects, expected to be JSON dicts
        naming_template (optional): error log naming template for module

    Returns:
        bool: True if error log updated successfully, else False
    """

    error_log_name = get_error_log_name(module=DefaultValues.ENROLLMENT_MODULE,
                                        input_data=input_record,
                                        naming_template=naming_template)

    if not error_log_name or not update_error_log_and_qc_metadata(
            error_log_name=error_log_name,
            destination_prj=project,
            gear_name=gear_name,
            state='PASS' if qc_passed else 'FAIL',
            errors=errors):
        raise GearExecutionError('Failed to update error log for visit '
                                 f'{input_record[FieldNames.PTID]}, '
                                 f'{input_record[FieldNames.ENRLFRM_DATE]}')


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
            log.warning('No enrollment records found to create')
            return

        query = [record.query_object() for record in self.__records.values()]
        identifiers = repo.create_list(query)
        log.info("created %s new NACCIDs", len(identifiers))
        if len(query) != len(identifiers):
            log.warning("expected %s new IDs, got %s", len(query),
                        len(identifiers))

        for identifier in identifiers:
            record = self.__records.get(identifier.ptid)
            if record:
                record.naccid = identifier.naccid


class TransferVisitor(CSVVisitor):
    """Visitor for processing transfers into a center."""

    def __init__(self, error_writer: ListErrorWriter,
                 transfer_info: TransferInfo,
                 repo: IdentifierRepository) -> None:
        self.__error_writer = error_writer
        self.__transfer_info = transfer_info
        self.__repo = repo
        self.__validator = NewPTIDRowValidator(repo, error_writer)
        self.__naccid_identifier: Optional[IdentifierObject] = None
        self.__naccid: Optional[str] = None
        self.__previous_identifiers: Optional[CenterIdentifiers] = None

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has expected column headings.

        Args:
          header: the list of column headings for file
        Returns:
          True if the header has expected columns, False otherwise.
        """
        expected_columns = {
            FieldNames.OLDADCID, FieldNames.OLDPTID, FieldNames.NACCIDKWN,
            FieldNames.NACCID, FieldNames.PREVENRL
        }
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_field_error(expected_columns))
            return False

        return True

    def _naccid_visit(self, row: Dict[str, Any], line_num: int) -> bool:
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

        self.__naccid = row[FieldNames.NACCID]
        if not self.__naccid:
            self.__error_writer.write(
                empty_field_error(FieldNames.NACCID, line_num))
            return False

        self.__naccid_identifier = self.__repo.get(naccid=self.__naccid)
        if self.__naccid_identifier:
            return True

        self.__error_writer.write(
            identifier_error(
                field=FieldNames.NACCID,
                value=self.__naccid,
                line=line_num,
                message=f"Did not find participant for NACCID {self.__naccid}")
        )
        return False

    def _match_naccid(self, identifier, source, line_num: int) -> bool:
        """Checks whether the identifier matches the NACCID in the visitor.

        Args:
          identifier: the identifier to match
          source: string describing source column for NACCID
          line_num: the line number
        Returns:
          True if the identifier matches the NACCID. False, otherwise.
        """
        if not self.__naccid_identifier:
            return False

        if identifier == self.__naccid_identifier:
            return True

        self.__error_writer.write(
            FileError(error_type='error',
                      error_code='mismatched-id',
                      location=CSVLocation(line=line_num,
                                           column_name=FieldNames.NACCID),
                      message=("mismatched NACCID for "
                               f"{source} "
                               f"and provided NACCID {self.__naccid}")))
        return False

    def _guid_visit(self, row: Dict[str, Any], line_num: int) -> bool:
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

        guid_identifier = self.__repo.get(guid=row[FieldNames.GUID])
        if not guid_identifier:
            self.__error_writer.write(
                identifier_error(
                    field=FieldNames.GUID,
                    value=row[FieldNames.GUID],
                    line=line_num,
                    message=f"No NACCID found for GUID {row[FieldNames.GUID]}")
            )
            return False
        if not self._match_naccid(guid_identifier, row[FieldNames.GUID],
                                  line_num):
            return False

        self.__naccid_identifier = guid_identifier

        return True

    def _prevenrl_visit(self, row: Dict[str, Any], line_num: int) -> bool:
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

        previous_adcid = row[FieldNames.OLDADCID]
        if previous_adcid is None:
            self.__error_writer.write(
                empty_field_error(FieldNames.OLDADCID, line_num))
            return False
        previous_ptid = row[FieldNames.OLDPTID]
        if not previous_ptid:
            self.__error_writer.write(
                empty_field_error(FieldNames.OLDPTID, line_num))
            return False

        ptid_identifier = self.__repo.get(adcid=previous_adcid,
                                          ptid=previous_ptid)
        if not ptid_identifier:
            self.__error_writer.write(
                identifier_error(
                    value=previous_ptid,
                    line=line_num,
                    message=(f"No NACCID found for ADCID {previous_adcid}, "
                             f"PTID {previous_ptid}")))
            return False

        if not self._match_naccid(ptid_identifier,
                                  f"{previous_adcid}-{previous_ptid}",
                                  line_num):
            return False

        self.__naccid_identifier = ptid_identifier
        self.__previous_identifiers = CenterIdentifiers(adcid=previous_adcid,
                                                        ptid=previous_ptid)
        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits enrollment/transfer data for single form.

        Args:
          row: the dictionary for the row in the file
          line_num: the line number of the row
        Returns:
          True if the row is a valid transfer. False, otherwise.
        """
        if not self.__validator.check(row, line_num):
            return True

        new_identifiers = CenterIdentifiers(adcid=row[FieldNames.ADCID],
                                            ptid=row[FieldNames.PTID])

        if not self._naccid_visit(row=row, line_num=line_num):
            return False

        if not self._guid_visit(row=row, line_num=line_num):
            return False

        if not self._prevenrl_visit(row=row, line_num=line_num):
            return False

        naccid = None
        if self.__naccid_identifier:
            naccid = self.__naccid_identifier.naccid

        try:
            enroll_date = parse_date(date_string=row[FieldNames.ENRLFRM_DATE],
                                     formats=DATE_FORMATS)
        except DateFormatException:
            self.__error_writer.write(
                unexpected_value_error(field=FieldNames.ENRLFRM_DATE,
                                       value=row[FieldNames.ENRLFRM_DATE],
                                       expected='',
                                       message='Expected valid datetime date',
                                       line=line_num))
            return False

        self.__transfer_info.add(
            TransferRecord(date=enroll_date,
                           initials=row[FieldNames.ENRLFRM_INITL],
                           center_identifiers=new_identifiers,
                           previous_identifiers=self.__previous_identifiers,
                           naccid=naccid))
        log.info('Transfer found on line %s', line_num)
        return True


class NewEnrollmentVisitor(CSVVisitor):
    """A CSV Visitor class for processing new enrollment forms."""

    def __init__(self, error_writer: ListErrorWriter,
                 repo: IdentifierRepository, batch: EnrollmentBatch) -> None:
        self.__batch = batch
        self.__validator = AggregateRowValidator([
            NewPTIDRowValidator(repo, error_writer),
            NewGUIDRowValidator(repo, error_writer)
        ])
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

        log.info('Adding new enrollment for (%s,%s)', row[FieldNames.ADCID],
                 row[FieldNames.PTID])
        try:
            enroll_date = parse_date(date_string=row[FieldNames.ENRLFRM_DATE],
                                     formats=DATE_FORMATS)
        except DateFormatException:
            self.__error_writer.write(
                unexpected_value_error(field=FieldNames.ENRLFRM_DATE,
                                       value=row[FieldNames.ENRLFRM_DATE],
                                       expected='',
                                       message='Expected valid datetime date',
                                       line=line_num))
            return False

        try:
            self.__batch.add(
                EnrollmentRecord(center_identifier=CenterIdentifiers(
                    adcid=row[FieldNames.ADCID], ptid=row[FieldNames.PTID]),
                                 guid=row.get(FieldNames.GUID)
                                 if row.get(FieldNames.GUID) else None,
                                 naccid=None,
                                 start_date=enroll_date))
            return True
        except ValidationError as validation_error:
            for error in validation_error.errors():
                if error['type'] == 'string_pattern_mismatch':
                    field_name = str(error['loc'][0])
                    context = error.get('ctx', {'pattern': ''})
                    self.__error_writer.write(
                        unexpected_value_error(
                            field=field_name,
                            value=error['input'],
                            expected=context['pattern'],
                            message=f'Invalid {field_name.upper()}',
                            line=line_num))

            return False


class ProvisioningVisitor(CSVVisitor):
    """A CSV Visitor class for processing participant enrollment and transfer
    forms."""

    def __init__(self, *, center_id: int, error_writer: ListErrorWriter,
                 transfer_info: TransferInfo, batch: EnrollmentBatch,
                 repo: IdentifierRepository, gear_name: str,
                 project: ProjectAdaptor) -> None:
        self.__error_writer = error_writer
        self.__project = project
        self.__gear_name = gear_name
        self.__enrollment_visitor = NewEnrollmentVisitor(error_writer,
                                                         repo=repo,
                                                         batch=batch)
        self.__transfer_in_visitor = TransferVisitor(
            error_writer, repo=repo, transfer_info=transfer_info)
        self.__validator = CenterValidator(center_id=center_id,
                                           error_writer=error_writer)
        self.__error_log_template = {
            "ptid": FieldNames.PTID,
            "visitdate": FieldNames.ENRLFRM_DATE
        }

    def visit_header(self, header: List[str]) -> bool:
        """Prepares visitor to work with CSV file with given header.

        Args:
          header: the list of header names
        Returns:
          True if all of the visitors return True. False otherwise
        """
        expected_columns = {
            FieldNames.PTID, FieldNames.ADCID, FieldNames.ENRLFRM_DATE,
            FieldNames.ENRLTYPE
        }
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_field_error(expected_columns))
            return False

        return (self.__enrollment_visitor.visit_header(header)
                and self.__transfer_in_visitor.visit_header(header))

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Provisions a NACCID for the ADCID and PTID.

        First checks that the row has the form name as the module.
        Then checks form to determine processing.
        If form is
        - a new enrollment, then applies the NewEnrollmentVisitor.
        - a transfer TransferVisitor.

        Args:
          row: the dictionary for the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if the row is a valid enrollment or transfer.  False, otherwise.
        """

        self.__error_writer.clear()
        try:
            if not self.__validator.check(row=row, line_number=line_num):
                update_record_level_error_log(
                    input_record=row,
                    qc_passed=False,
                    project=self.__project,
                    gear_name=self.__gear_name,
                    errors=self.__error_writer.errors(),
                    naming_template=self.__error_log_template)
                return False

            if is_new_enrollment(row):
                success = self.__enrollment_visitor.visit_row(
                    row=row, line_num=line_num)
                if not success:  # Only update record level log if validation failed
                    update_record_level_error_log(
                        input_record=row,
                        qc_passed=False,
                        project=self.__project,
                        gear_name=self.__gear_name,
                        errors=self.__error_writer.errors(),
                        naming_template=self.__error_log_template)
                return success
        except IdentifierRepositoryError as error:
            message = (
                f'Failed to assign a NACCID for PTID {row[FieldNames.PTID]}: {error}'
            )
            log.error(message)
            self.__error_writer.write(
                identifier_error(message=message,
                                 field=FieldNames.PTID,
                                 value=row[FieldNames.PTID],
                                 line=line_num))
            update_record_level_error_log(
                input_record=row,
                qc_passed=False,
                project=self.__project,
                gear_name=self.__gear_name,
                errors=self.__error_writer.errors(),
                naming_template=self.__error_log_template)
            return False

        # No further processing implemented for transfers, so update visit level log
        # TODO - need to change when processing transfers implemented
        success = self.__transfer_in_visitor.visit_row(row=row,
                                                       line_num=line_num)
        update_record_level_error_log(
            input_record=row,
            qc_passed=success,
            project=self.__project,
            gear_name=self.__gear_name,
            errors=self.__error_writer.errors(),
            naming_template=self.__error_log_template)
        return success


def run(*, input_file: TextIO, center_id: int, repo: IdentifierRepository,
        enrollment_project: EnrollmentProject, error_writer: ListErrorWriter,
        gear_name: str):
    """Runs identifier provisioning process.

    Args:
      input_file: the data input stream
      center_id: the ADCID for the center
      repo: the identifier repository
      enrollment_project: the project tracking enrollment
      error_writer: the error output writer
      gear_name: gear name
    """
    transfer_info = TransferInfo(transfers=[])
    enrollment_batch = EnrollmentBatch()
    try:
        success = read_csv(input_file=input_file,
                           error_writer=error_writer,
                           visitor=ProvisioningVisitor(
                               center_id=center_id,
                               batch=enrollment_batch,
                               repo=repo,
                               error_writer=error_writer,
                               transfer_info=transfer_info,
                               gear_name=gear_name,
                               project=enrollment_project),
                           clear_errors=True)
        if not success:
            log.warning("Some records in the input file failed validation. "
                        "Check record level QC status.")

        log.info(
            "Requesting new NACCIDs for %s successfully validated records",
            len(enrollment_batch))
        enrollment_batch.commit(repo)
    except IdentifierRepositoryError as error:
        raise GearExecutionError(error) from error

    for record in enrollment_batch:
        error_writer.clear()
        record_info = {
            'ptid': record.center_identifier.ptid,
            'visitdate': record.start_date.strftime("%Y-%m-%d")
        }
        if not record.naccid:
            message = ('Failed to generate NACCID for enrollment record '
                       f'{record.center_identifier.adcid},'
                       f'{record.center_identifier.ptid}')
            log.error(message)
            error_writer.write(system_error(message=message))
            update_record_level_error_log(input_record=record_info,
                                          qc_passed=False,
                                          project=enrollment_project,
                                          gear_name=gear_name,
                                          errors=error_writer.errors())

            success = False
            continue

        if enrollment_project.find_subject(label=record.naccid):
            message = f'Subject with NACCID {record.naccid} exists'
            log.error(message)
            error_writer.write(system_error(message=message))
            update_record_level_error_log(input_record=record_info,
                                          qc_passed=False,
                                          project=enrollment_project,
                                          gear_name=gear_name,
                                          errors=error_writer.errors())
            success = False
            continue

        subject = enrollment_project.add_subject(record.naccid)
        subject.add_enrollment(record)
        # subject.update_demographics_info(demographics)

        update_record_level_error_log(input_record=record_info,
                                      qc_passed=True,
                                      project=enrollment_project,
                                      gear_name=gear_name,
                                      errors=error_writer.errors())

    # TODO - add record level error reporting when implementing transfer processing
    enrollment_project.add_transfers(transfer_info)

    if not success:
        error_writer.clear()
        error_writer.write(partially_failed_file_error())

    return success
