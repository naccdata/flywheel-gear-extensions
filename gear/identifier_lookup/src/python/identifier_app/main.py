"""Defines the NACCID lookup computation."""

import logging
from typing import Any, Dict, List, Optional, TextIO

from identifiers.model import IdentifierObject
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import ErrorWriter, identifier_error, missing_header_error
from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)


class IdentifierVisitor(CSVVisitor):
    """A CSV Visitor class for adding a NACCID to the rows of a CSV input.

    Requires the input CSV has a PTID column, and all rows represent
    data from same ADRC (have the same ADCID).
    """

    def __init__(self, *, identifiers: Dict[str, IdentifierObject],
                 output_file: TextIO, module_name: str,
                 error_writer: ErrorWriter) -> None:
        """
        Args:
          identifiers: the map from PTID to Identifier object
          output_file: the data output stream
          error_writer: the error output writer
        """
        self.__identifiers = identifiers
        self.__output_file = output_file
        self.__error_writer = error_writer
        self.__module_name = module_name
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None

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

        If the header doesn't have `ptid`, returns an error.

        Args:
          header: the list of header names
        Returns:
          True if `ptid` occurs in the header, False otherwise
        """
        if FieldNames.PTID not in header:
            self.__error_writer.write(missing_header_error())
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
        writer = self.__get_writer()

        identifier = self.__identifiers.get(row[FieldNames.PTID])
        if not identifier:
            self.__error_writer.write(
                identifier_error(line=line_num, value=row[FieldNames.PTID]))
            return False

        row[FieldNames.NACCID] = identifier.naccid
        row[FieldNames.MODULE] = self.__module_name

        writer.write(row)

        return True


def run(*, input_file: TextIO, identifiers: Dict[str, IdentifierObject],
        module_name: str, output_file: TextIO,
        error_writer: ErrorWriter) -> bool:
    """Reads participant records from the input CSV file, finds the NACCID for
    each row from the ADCID and PTID, and outputs a CSV file with the NACCID
    inserted.

    If the NACCID isn't found for a row, an error is written to the error file.

    Note: this function assumes that the ADCID for each row is the same, and
    that the ADCID corresponds to the ID for the group where the file is
    located.
    The identifiers map should at least include Identifiers objects with this
    ADCID.

    Args:
      input_file: the data input stream
      identifiers: the map from PTID to Identifier object
      output_file: the data output stream
      error_writer: the error output writer
    Returns:
      True if there were IDs with no corresponding NACCID
    """

    return read_csv(input_file=input_file,
                    error_writer=error_writer,
                    visitor=IdentifierVisitor(identifiers=identifiers,
                                              output_file=output_file,
                                              module_name=module_name,
                                              error_writer=error_writer))
