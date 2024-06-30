"""Defines Identifier Provisioning."""

import logging
from typing import Any, Dict, Iterator, List, Optional, TextIO

from enrollment.enrollment_project import EnrollmentProject, TransferInfo
from enrollment.enrollment_transfer import (
    CenterValidator, EnrollmentRecord, NewGUIDRowValidator,
    NewPTIDRowValidator, TransferRecord, guid_available, has_known_naccid,
    is_new_enrollment, previously_enrolled)
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (IdentifierRepository,
                                                IdentifierRepositoryError)
from identifiers.model import CenterIdentifiers, IdentifierObject
from inputs.csv_reader import AggregateRowValidator, CSVVisitor, read_csv
from outputs.errors import (CSVLocation, ErrorWriter, FileError,
                            empty_field_error, identifier_error,
                            missing_header_error)

log = logging.getLogger(__name__)


class EnrollmentBatch:
    """Collects new Identifier objects for commiting to repository."""

    def __init__(self) -> None:
        self.__records: Dict[str, EnrollmentRecord] = {}

    def __iter__(self) -> Iterator[EnrollmentRecord]:
        """Returns an iterator to the the enrollment records in this batch."""
        return iter(self.__records.values())

    def __len__(self) -> int:
        """Returns the number of enrollment records in this batch."""
        return len(self.__records.values())

    def add(self, enrollment_record: EnrollmentRecord) -> None:
        """Adds the enrollment object to this bacth.

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

    def __init__(self, error_writer: ErrorWriter, transfer_info: TransferInfo,
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
            'oldadcid', 'oldptid', 'naccidknwn', 'naccid', 'prevenrl'
        }
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_header_error())
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
          True if the rows has no expected NACCID, or the NACCID in the row exists. False otherwise.
        """
        if not has_known_naccid(row):
            return True

        self.__naccid = row['naccid']
        if not self.__naccid:
            self.__error_writer.write(empty_field_error('naccid', line_num))
            return False

        self.__naccid_identifier = self.__repo.get(naccid=self.__naccid)
        if self.__naccid_identifier:
            return True

        self.__error_writer.write(
            identifier_error(
                field='naccid',
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
                                           column_name='naccid'),
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
          True if either the row does not have an expected GUID, or the GUID exists and is for same participant as other identifiers. False otherwise.
        """
        if not guid_available(row):
            return True

        guid_identifier = self.__repo.get(guid=row['guid'])
        if not guid_identifier:
            self.__error_writer.write(
                identifier_error(
                    field='guid',
                    value=row['guid'],
                    line=line_num,
                    message=f"No NACCID found for GUID {row['guid']}"))
            return False
        if not self._match_naccid(guid_identifier, row['guid'], line_num):
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
          True if either the row does not indicate a previous enrollment, or the provided identifiers correspond to the same participant as other identifiers. False otherwise.
        """
        if not previously_enrolled(row):
            return True

        previous_adcid = row['oldadcid']
        if previous_adcid is None:
            self.__error_writer.write(empty_field_error('oldadcid', line_num))
            return False
        previous_ptid = row['oldptid']
        if not previous_ptid:
            self.__error_writer.write(empty_field_error('oldptid', line_num))
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

        new_identifiers = CenterIdentifiers(adcid=row['adcid'],
                                            ptid=row['ptid'])

        if not self._naccid_visit(row=row, line_num=line_num):
            return False

        if not self._guid_visit(row=row, line_num=line_num):
            return False

        if not self._prevenrl_visit(row=row, line_num=line_num):
            return False

        naccid = None
        if self.__naccid_identifier:
            naccid = self.__naccid_identifier.naccid
        self.__transfer_info.add(
            TransferRecord(date=row['frmdate_enrl'],
                           initials=row['initials_enrl'],
                           center_identifiers=new_identifiers,
                           previous_identifiers=self.__previous_identifiers,
                           naccid=naccid))

        log.info('Transfer found on line %s', line_num)

        return True


class NewEnrollmentVisitor(CSVVisitor):
    """A CSV Visitor class for processing new enrollment forms."""

    def __init__(self, error_writer: ErrorWriter, repo: IdentifierRepository,
                 batch: EnrollmentBatch) -> None:
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
        expected_columns = {'adcid', 'ptid', 'guid'}
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_header_error())
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

        log.info('Adding new enrollment for (%s,%s)', row['adcid'],
                 row['ptid'])
        self.__batch.add(EnrollmentRecord.create_from(row))

        return True


class ProvisioningVisitor(CSVVisitor):
    """A CSV Visitor class for processing participant enrollment and transfer
    forms."""

    def __init__(self, *, center_id: int, error_writer: ErrorWriter,
                 transfer_info: TransferInfo, batch: EnrollmentBatch,
                 repo: IdentifierRepository) -> None:
        self.__error_writer = error_writer
        self.__enrollment_visitor = NewEnrollmentVisitor(error_writer,
                                                         repo=repo,
                                                         batch=batch)
        self.__transfer_in_visitor = TransferVisitor(
            error_writer, repo=repo, transfer_info=transfer_info)
        self.__validator = CenterValidator(center_id=center_id,
                                           error_writer=error_writer)

    def visit_header(self, header: List[str]) -> bool:
        """Prepares visitor to work with CSV file with given header.

        Args:
          header: the list of header names
        Returns:
          True if all of the visitors return True. False otherwise
        """
        expected_columns = {'enrltype'}
        if not expected_columns.issubset(set(header)):
            self.__error_writer.write(missing_header_error())
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
          True if the row represents a valid enrollment or transfer. False, otherwise.
        """
        if not self.__validator.check(row=row, line_number=line_num):
            return False

        if is_new_enrollment(row):
            return self.__enrollment_visitor.visit_row(row=row,
                                                       line_num=line_num)

        return self.__transfer_in_visitor.visit_row(row=row, line_num=line_num)


def run(*, input_file: TextIO, center_id: int, repo: IdentifierRepository,
        enrollment_project: EnrollmentProject, error_writer: ErrorWriter):
    """Runs identifier provisioning process.

    Args:
      input_file: the data input stream
      center_id: the ADCID for the center
      repo: the identifier repository
      enrollment_project: the project tracking enrollment
      error_writer: the error output writer
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
                                 transfer_info=transfer_info))
        if not success:
            log.error("no changes made due to errors in input file")
            return True

        log.info("requesting %s new NACCIDs", len(enrollment_batch))
        enrollment_batch.commit(repo)
    except IdentifierRepositoryError as error:
        raise GearExecutionError(error) from error

    for record in enrollment_batch:
        if not record.naccid:
            log.error('Failed to generate NACCID for enrollment record %s/%s',
                      record.center_identifier.adcid,
                      record.center_identifier.ptid)
            continue

        if enrollment_project.find_subject(label=record.naccid):
            log.error('Subject with NACCID %s exists', record.naccid)
            continue

        subject = enrollment_project.add_subject(record.naccid)
        subject.add_enrollment(record)
        # subject.update_demographics_info(demographics)

    enrollment_project.add_transfers(transfer_info)

    return True
