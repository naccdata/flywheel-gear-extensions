"""Defines the NACCID lookup computation."""

import logging
import time
from typing import Any, Dict, List, Optional, TextIO

from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject, clean_ptid
from inputs.csv_reader import CSVVisitor, RowValidator, read_csv
from nacc_common.error_models import FileError
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    identifier_error,
    missing_field_error,
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
        identifiers_repo: IdentifierRepository,
        output_file: TextIO,
        module_name: str,
        required_fields: Optional[List[str]],
        error_writer: ListErrorWriter,
        misc_errors: List[FileError],
        validator: Optional[RowValidator] = None,
    ) -> None:
        """
        Args:
            identifiers_repo: identifiers repo to pull identifiers from
            output_file: the data output stream
            module_name: the module name for the form
            required_fields: list of required fields for header validation
            error_writer: the error output writer
            misc_errors: list to store errors occur while updating visit error log
            validator: optional row validator for ADCID and PTID validation
        """
        self.__identifiers_repo = identifiers_repo
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__module_name = module_name
        self.__required_fields = required_fields
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None
        self.__validator = validator
        self.__misc_errors = misc_errors

        self.__identifiers_cache: Dict[str, Dict[str, IdentifierObject]] = {}

    def __get_identifiers(self, adcid: int) -> Dict[str, IdentifierObject]:
        """Gets all of the Identifier objects from the identifier database for the
        specified center.

        Args:
          adcid: the ADCID for the center

        Returns:
          the dictionary mapping from PTID to Identifier object
        """
        identifiers = {}
        center_identifiers = self.__identifiers_repo.list(adcid=adcid)
        if center_identifiers:
            identifiers = {identifier.ptid: identifier for identifier in center_identifiers}

        return identifiers

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

        if self.__required_fields:
            req_fields = set(self.__required_fields)
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

        # check for valid ADCID and PTID if validator is provided
        if self.__validator and not self.__validator.check(
            row=row, line_number=line_num
        ):
            return False

        ptid = clean_ptid(row[FieldNames.PTID])

        try:
            adcid = int(row[FieldNames.ADCID])
        except (ValueError, TypeError) as e:
            self.__error_writer.write(
                unexpected_value_error(
                    field=FieldNames.ADCID,
                    value=row[FieldNames.ADCID],
                    expected="integer ADCID",
                    line=line_num,
                    message="non-integer ADCID",
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )

        if adcid not in self.__identifiers_cache:
            self.__identifiers_cache[adcid] = self.__get_identifiers(adcid)

        identifier = self.__identifiers_cache[adcid].get(ptid)
        if not identifier:
            self.__error_writer.write(
                identifier_error(
                    line=line_num,
                    value=ptid,
                    message="No matching NACCID found for the given PTID",
                )
            )
            return False

        row[FieldNames.NACCID] = identifier.naccid
        row[FieldNames.MODULE] = self.__module_name

        writer = self.__get_writer()
        writer.write(row)

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
        batch_size: int = 1000,
    ) -> None:
        self.__identifiers_repo = identifiers_repo
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__writer: Optional[CSVWriter] = None
        self.__header: Optional[List[str]] = None
        self.__batch_size = batch_size  # set to -1 to disable

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

        # sleep for 1 seconds per batch size to reduce concurrent connections
        if self.__batch_size > 0 and line_num % self.__batch_size == 0:
            time.sleep(1)

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
