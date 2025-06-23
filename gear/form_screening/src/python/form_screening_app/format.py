"""Module for formatting CSV file."""

from typing import Any, Dict, List, Optional, TextIO

from inputs.csv_reader import CSVVisitor
from keys.keys import REDCapKeys
from outputs.errors import ErrorWriter, malformed_file_error
from outputs.outputs import CSVWriter


class CSVFormatException(Exception):
    pass


class CSVFormatterVisitor(CSVVisitor):
    """This class formats the input CSV."""

    def __init__(self, *, output_stream: TextIO,
                 error_writer: ErrorWriter) -> None:
        self.__out_stream = output_stream
        self.__error_writer = error_writer
        self.__org_header_length = -1
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None

    def __get_writer(self) -> CSVWriter:
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(stream=self.__out_stream,
                                      fieldnames=self.__header)

        return self.__writer

    def __validate_header(self, header: List[str]) -> bool:
        """Validates the header. Returns the list of duplicate columns in the
        header, if any.

        Args:
            header: CSV file header

        Returns:
            bool: False if header is not valid
        """
        seen = set()
        duplicates = []
        empty_cols = []
        for index, column in enumerate(header):
            if not len(column.strip()) > 0:
                empty_cols.append(index)
                continue

            if column in seen:
                if column not in duplicates:
                    duplicates.append(column)
            else:
                seen.add(column)

        if empty_cols:
            self.__error_writer.write(
                malformed_file_error(
                    error=
                    f'File header contains empty string at column indices {empty_cols}'
                ))

        if duplicates:
            self.__error_writer.write(
                malformed_file_error(
                    error=
                    f'Duplicate column names {duplicates} detected in the file header'
                ))

        return not (duplicates or empty_cols)

    def visit_header(self, header: List[str]) -> bool:
        """Convert the header to lowercase. Remove any REDCap specific columns
        form the header.

        Args:
          header: the list of header names

        Returns:
          True
        """

        if not self.__validate_header(header):
            return False

        self.__org_header_length = len(header)

        self.__header = [
            column.strip().lower() for column in header
            if column.lower() not in REDCapKeys
        ]

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Remove any REDCap specific columns form the row.

        Args:
          header: the list of header names

        Returns:
          True
        """

        if len(row) != self.__org_header_length:
            message = (
                f'Number of columns in line {line_num} '
                f'do not match with the number of columns in the header row')
            raise CSVFormatException(message)

        out_row = {
            key.strip().lower(): value
            for key, value in row.items() if key.lower() not in REDCapKeys
        }

        writer = self.__get_writer()
        writer.write(out_row)

        return True
