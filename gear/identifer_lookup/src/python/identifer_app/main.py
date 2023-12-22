"""Defines the NACCID lookup computation."""

import logging
from typing import Any, Dict, List, TextIO

from identifiers.model import Identifier
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import ErrorWriter, identifier_error, missing_header_error
from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)

PTID = 'ptid'
NACCID = 'naccid'


class IdentifierWriter(CSVVisitor):
    """Visitor that adds NACCID to input row."""

    def __init__(self, stream: TextIO, identifiers: Dict[str, Identifier],
                 error_writer: ErrorWriter) -> None:
        self.__stream = stream
        self.__identifiers = identifiers
        self.__error_writer = error_writer
        self.__writer = None
        self.__header = []

    def __get_writer(self):
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(stream=self.__stream,
                                      fieldnames=self.__header)

        return self.__writer

    def visit(self, record: Dict[str, Any], line_num: int) -> bool:
        """Visits a record in CSV file and adds the NACCID corresponding to the
        PTID.

        Writes any errors to the error_writer of the visitor object.

        Note: ADCID is implicit to context of use.

        Args:
          record: the dict for a row of CSV file
          line_num: the row number for the record
        Returns:
          True if the NACCID is not found, False otherwise
        """
        writer = self.__get_writer()

        identifier = self.__identifiers.get(record[PTID])
        if not identifier:
            self.__error_writer.write(
                identifier_error(line=line_num, value=record[PTID]))
            return True

        record[NACCID] = identifier.naccid
        writer.write(record)

        return False

    def add_header(self, header: List[str]) -> bool:
        """Adds the header fields to the visitor object.

        Args:
          header: the list of header fields
        Returns:
          True if the header does not include the PTID, False otherwise.
        """
        if PTID not in header:
            self.__error_writer.write(missing_header_error())
            return True

        self.__header = header
        self.__header.append(NACCID)

        return False


def run(*, input_file: TextIO, identifiers: Dict[str, Identifier],
        output_file: TextIO, error_writer: ErrorWriter) -> bool:
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
                    visitor=IdentifierWriter(stream=output_file,
                                             identifiers=identifiers,
                                             error_writer=error_writer))
