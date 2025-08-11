"""Defines the NACCID lookup computation."""

import logging
from typing import Any, Dict, List, Optional, TextIO

from configs.ingest_configs import ErrorLogTemplate, ModuleConfigs
from enrollment.enrollment_transfer import CenterValidator
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject, clean_ptid
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.error_logger import update_error_log_and_qc_metadata
from outputs.error_models import FileError, VisitKeys
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    identifier_error,
    missing_field_error,
    system_error,
    unexpected_value_error,
)
from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)


class NACCIDLookupVisitor(CSVVisitor):
    """A CSV Visitor class for adding a NACCID to the rows of a CSV input.

    Requires the input CSV has a PTID column, and all rows represent
    data from same ADRC (have the same ADCID).
    """

    def __init__(
        self,
        *,
        adcid: int,
        identifiers: Dict[str, IdentifierObject],
        output_file: TextIO,
        module_name: str,
        module_configs: ModuleConfigs,
        error_writer: ListErrorWriter,
        gear_name: str,
        misc_errors: List[FileError],
        project: Optional[ProjectAdaptor] = None,
    ) -> None:
        """
        Args:
            adcid: ADCID for the center
            identifiers: the map from PTID to Identifier object
            output_file: the data output stream
            module_name: the module name for the form
            module_configs: form ingest configurations for the module
            error_writer: the error output writer
            gear_name: gear name
            misc_errors: list to store errors occur while updating visit error log
            project: Flywheel project adaptor
        """
        self.__identifiers = identifiers
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__module_name = module_name
        self.__module_configs = module_configs
        self.__project = project
        self.__gear_name = gear_name
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None
        self.__validator = CenterValidator(
            center_id=adcid,
            date_field=module_configs.date_field,
            error_writer=error_writer,
        )
        self.__misc_errors = misc_errors

    def __get_writer(self) -> CSVWriter:
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(
                stream=self.__output_file, fieldnames=self.__header
            )

        return self.__writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to write a CSV file with the given header.

        If the header doesn't have required fields returns an error.

        Args:
          header: the list of header names

        Returns:
          True if required fields occur in the header, False otherwise
        """

        if self.__module_configs.required_fields:
            req_fields = set(self.__module_configs.required_fields)
            if not req_fields.issubset(set(header)):
                self.__error_writer.write(missing_field_error(req_fields))
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

        # processing a new row, clear previous errors if any
        self.__error_writer.clear()

        # check for valid ADCID and PTID
        if not self.__validator.check(row=row, line_number=line_num):
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        ptid = clean_ptid(row[FieldNames.PTID])
        identifier = self.__identifiers.get(ptid)
        if not identifier:
            self.__error_writer.write(
                identifier_error(
                    line=line_num,
                    value=ptid,
                    message="No matching NACCID found for the given PTID",
                )
            )
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        row[FieldNames.NACCID] = identifier.naccid
        row[FieldNames.MODULE] = self.__module_name

        if not self.__update_visit_error_log(input_record=row, qc_passed=True):
            return False

        writer = self.__get_writer()
        writer.write(row)

        return True

    def __update_visit_error_log(
        self, *, input_record: Dict[str, Any], qc_passed: bool
    ) -> bool:
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks

        Returns:
            bool: False if errors occur while updating log file
        """

        if not self.__project:
            raise GearExecutionError(
                "Parent project not specified to upload visit error log"
            )

        errorlog_template = (
            self.__module_configs.errorlog_template
            if self.__module_configs.errorlog_template
            else ErrorLogTemplate(
                id_field=FieldNames.PTID, date_field=self.__module_configs.date_field
            )
        )
        error_log_name = errorlog_template.instantiate(
            module=self.__module_name, record=input_record
        )

        if not error_log_name:
            message = (
                f"Invalid values found for "
                f"{FieldNames.PTID} ({input_record[FieldNames.PTID]}) or "
                f"{self.__module_configs.date_field} "
                f"({input_record[self.__module_configs.date_field]})"
            )
            self.__misc_errors.append(
                unexpected_value_error(
                    field=f"{FieldNames.PTID} or {self.__module_configs.date_field}",
                    value="",
                    expected="",
                    message=message,
                )
            )
            return False

        # This is first gear in pipeline validating individual rows
        # therefore, clear metadata from previous runs `reset_qc_metadata=ALL`
        if not update_error_log_and_qc_metadata(
            error_log_name=error_log_name,
            destination_prj=self.__project,
            gear_name=self.__gear_name,
            state="PASS" if qc_passed else "FAIL",
            errors=self.__error_writer.errors(),
            reset_qc_metadata="ALL",
        ):
            message = (
                "Failed to update error log for visit "
                f"{input_record[FieldNames.PTID]}_{input_record[self.__module_configs.date_field]}"
            )
            self.__misc_errors.append(
                system_error(
                    message=message,
                    visit_keys=VisitKeys.create_from(
                        record=input_record, date_field=self.__module_configs.date_field
                    ),
                )
            )
            return False

        return True


class CenterLookupVisitor(CSVVisitor):
    """Defines a CSV visitor class for adding ADCID, PTID to the rows of CSV
    input.

    Requires the input CSV has a NACCID column
    """

    def __init__(
        self,
        *,
        identifiers_repo: IdentifierRepository,
        output_file: TextIO,
        error_writer: ListErrorWriter,
    ) -> None:
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
            self.__writer = CSVWriter(
                stream=self.__output_file, fieldnames=self.__header
            )

        return self.__writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to write a CSV file with the given header.

        If the header doesn't have `naccid`, returns an error.

        Args:
          header: the list of header names
        Returns:
          True if `naccid` occurs in the header, False otherwise
        """
        if FieldNames.NACCID not in header and FieldNames.NACCID.upper() not in header:
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
        naccid = row.get(FieldNames.NACCID, row.get(FieldNames.NACCID.upper(), None))

        if naccid is None:
            raise GearExecutionError(f"NACCID not found in row {line_num}")

        try:
            identifier = self.__identifiers_repo.get(naccid=naccid)
        except (IdentifierRepositoryError, TypeError) as error:
            raise GearExecutionError(f"Lookup of {naccid} failed: {error}") from error

        if not identifier:
            self.__error_writer.write(
                identifier_error(line=line_num, value=naccid, field=FieldNames.NACCID)
            )
            return False

        row[FieldNames.ADCID] = identifier.adcid
        row[FieldNames.PTID] = identifier.ptid

        writer = self.__get_writer()
        writer.write(row)

        return True


def run(
    *,
    input_file: TextIO,
    error_writer: ListErrorWriter,
    lookup_visitor: CSVVisitor,
    clear_errors: bool = False,
    preserve_case: bool = False,
) -> bool:
    """Reads participant records from the input CSV file and applies the ID
    lookup visitor to insert corresponding IDs.

    Args:
      input_file: the data input stream
      lookup_visitor: the CSVVisitor for identifier lookup
      error_writer: the error output writer
      clear_errors: clear the accumulated error metadata
      preserve_case: Whether or not to preserve header key case while reading
        in the CSV file

    Returns:
      True if there were IDs with no corresponding ID by lookup visitor
    """

    return read_csv(
        input_file=input_file,
        error_writer=error_writer,
        visitor=lookup_visitor,
        clear_errors=clear_errors,
        preserve_case=preserve_case,
    )
