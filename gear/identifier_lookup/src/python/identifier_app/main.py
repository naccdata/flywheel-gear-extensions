"""Defines the NACCID lookup computation."""

import logging
from typing import Any, Dict, List, Optional, TextIO

from enrollment.enrollment_transfer import CenterValidator
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import (
    ListErrorWriter,
    get_error_log_name,
    identifier_error,
    missing_field_error,
    update_error_log_and_qc_metadata,
)
from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)


class NACCIDLookupVisitor(CSVVisitor):
    """A CSV Visitor class for adding a NACCID to the rows of a CSV input.

    Requires the input CSV has a PTID column, and all rows represent
    data from same ADRC (have the same ADCID).
    """

    def __init__(self,
                 *,
                 adcid: int,
                 identifiers: Dict[str, IdentifierObject],
                 output_file: TextIO,
                 module_name: str,
                 error_writer: ListErrorWriter,
                 date_field: str,
                 gear_name: str,
                 project: Optional[ProjectAdaptor] = None) -> None:
        """
        Args:
            adcid: ADCID for the center
            identifiers: the map from PTID to Identifier object
            output_file: the data output stream
            module_name: the module name for the form
            error_writer: the error output writer
            date_field: visit date field for the module
            gear_name: gear name
            project: Flywheel project adaptor
        """
        self.__identifiers = identifiers
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__module_name = module_name
        self.__date_field = date_field
        self.__project = project
        self.__gear_name = gear_name
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None
        self.__validator = CenterValidator(center_id=adcid,
                                           error_writer=error_writer)
        self.__req_fields = {
            FieldNames.PTID, FieldNames.ADCID, self.__date_field
        }
        self.__error_log_template = {
            "ptid": FieldNames.PTID,
            "visitdate": self.__date_field
        }

    def __get_writer(self) -> CSVWriter:
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(stream=self.__output_file,
                                      fieldnames=self.__header)

        return self.__writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to write a CSV file with the given header.

        If the header doesn't have required fields returns an error.

        Args:
          header: the list of header names

        Returns:
          True if required fields occur in the header, False otherwise
        """

        if not self.__req_fields.issubset(set(header)):
            self.__error_writer.write(missing_field_error(self.__req_fields))
            return False

        self.__header = header
        self.__header.append(FieldNames.NACCID)
        self.__header.append(FieldNames.MODULE)

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Finds the NACCID for the row from the PTID, and outputs a row to a
        CSV file with the NACCID inserted.

        If the NACCID isn't found for a row, an error is written to the error
        file.

        Args:
          row: the dictionary from the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if there is a NACCID for the PTID, False otherwise
        """

        self.__error_writer.clear()

        # check for valid ADCID and PTID
        if not self.__validator.check(row=row, line_number=line_num):
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        identifier = self.__identifiers.get(row[FieldNames.PTID])
        if not identifier:
            self.__error_writer.write(
                identifier_error(
                    line=line_num,
                    value=row[FieldNames.PTID],
                    message='No matching NACCID found for the given PTID'))
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        row[FieldNames.NACCID] = identifier.naccid
        row[FieldNames.MODULE] = self.__module_name

        writer = self.__get_writer()
        writer.write(row)
        self.__update_visit_error_log(input_record=row, qc_passed=True)

        return True

    def __update_visit_error_log(self, *, input_record: Dict[str, Any],
                                 qc_passed: bool):
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks

        Returns:
            bool: True if error log updated successfully, else False
        """

        if not self.__project:
            log.warning(
                'Parent project not specified to upload visit error log')
            return

        error_log_name = get_error_log_name(
            module=self.__module_name,
            input_data=input_record,
            naming_template=self.__error_log_template)

        # This is first gear in pipeline validating individual rows
        # therefore, clear metadata from previous runs `reset_metadata=True`
        if not error_log_name or not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=self.__project,
                gear_name=self.__gear_name,
                state='PASS' if qc_passed else 'FAIL',
                errors=self.__error_writer.errors(),
                reset_metadata=True):
            raise GearExecutionError(
                'Failed to update error log for visit '
                f'{input_record[FieldNames.PTID]}, {input_record[self.__date_field]}'
            )


class CenterLookupVisitor(CSVVisitor):
    """Defines a CSV visitor class for adding ADCID, PTID to the rows of CSV
    input.

    Requires the input CSV has a NACCID column
    """

    def __init__(self, *, identifiers_repo: IdentifierRepository,
                 output_file: TextIO, error_writer: ListErrorWriter) -> None:
        self.__identifiers_repo = identifiers_repo
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__writer: Optional[CSVWriter] = None
        self.__header: Optional[List[str]] = None

    def __get_writer(self):
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(stream=self.__output_file,
                                      fieldnames=self.__header)

        return self.__writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to write a CSV file with the given header.

        If the header doesn't have `naccid`, returns an error.

        Args:
          header: the list of header names
        Returns:
          True if `naccid` occurs in the header, False otherwise
        """
        if (FieldNames.NACCID not in header
                and FieldNames.NACCID.upper() not in header):
            self.__error_writer.write(missing_field_error(FieldNames.NACCID))
            return False

        self.__header = header
        self.__header.append(FieldNames.ADCID)
        self.__header.append(FieldNames.PTID)

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Finds the ADCID, PTID for the row from the NACCID, and outputs a row
        to a CSV file with the ADCID and PTID inserted.

        If the ADCID, PTID are not found for a row, an error is written to the
        error file.

        Args:
          row: the dictionary from the CSV row (DictReader)
          line_num: the line number of the row
        Returns
          True if there is a ADCID, PTID for the NACCID. False otherwise.
        Raises:
          GearExecutionError if the identifiers repository raises an error
        """
        row = {key.strip().lower(): value for key, value in row.items()}

        try:
            identifier = self.__identifiers_repo.get(
                naccid=row[FieldNames.NACCID])
        except IdentifierRepositoryError as error:
            raise GearExecutionError(
                f"Lookup of {row[FieldNames.NACCID]} failed: {error}"
            ) from error

        if not identifier:
            self.__error_writer.write(
                identifier_error(line=line_num, value=row[FieldNames.NACCID]))
            return False

        row[FieldNames.ADCID] = identifier.adcid
        row[FieldNames.PTID] = identifier.ptid

        writer = self.__get_writer()
        writer.write(row)

        return True


def run(*,
        input_file: TextIO,
        error_writer: ListErrorWriter,
        lookup_visitor: CSVVisitor,
        clear_errors: bool = False) -> bool:
    """Reads participant records from the input CSV file and applies the ID
    lookup visitor to insert corresponding IDs.

    Args:
      input_file: the data input stream
      lookup_visitor: the CSVVisitor for identifier lookup
      error_writer: the error output writer
      clear_errors: clear the accumulated error metadata

    Returns:
      True if there were IDs with no corresponding ID by lookup visitor
    """

    return read_csv(input_file=input_file,
                    error_writer=error_writer,
                    visitor=lookup_visitor,
                    clear_errors=clear_errors)
