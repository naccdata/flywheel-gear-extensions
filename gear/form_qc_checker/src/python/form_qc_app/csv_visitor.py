"""Helper module for processing CSV files."""

from csv import Dialect, DictReader, Error, Sniffer
from typing import Any, Dict, List, Optional, TextIO

from inputs.csv_reader import CSVVisitor
from outputs.errors import (ErrorWriter, empty_field_error, empty_file_error,
                            malformed_file_error, missing_field_error,
                            missing_header_error)


class FormQCCSVVisitor(CSVVisitor):
    """Class to validate form data uploaded as a CSV file.

    Requires the input CSV has primary-key column and module column.
    """

    def __init__(self, pk_field: str, error_writer: ErrorWriter) -> None:
        """
        Args:
          pk_field: primary key field for the project/module
          error_writer: the error output writer
        """
        self.__pk_field = pk_field
        self.__error_writer = error_writer
        self.__header: Optional[List[str]] = None
        self.__reader: Optional[DictReader] = None
        self.__dialect: Optional[Dialect] = None

    @property
    def header(self) -> Optional[List[str]]:
        """Returns header columns list."""
        return self.__header

    @property
    def reader(self) -> Optional[DictReader]:
        """Returns reader."""
        return self.__reader

    @reader.setter
    def reader(self, reader: DictReader):
        """Set the reader.

        Args:
            reader: csv DictReader
        """

        self.__reader = reader

    @property
    def dialect(self) -> Optional[Dialect]:
        """Returns dialect."""
        return self.__dialect

    @dialect.setter
    def dialect(self, dialect: Dialect):
        """Set the dialect.

        Args:
            dialect: csv Dialect
        """

        self.__dialect = dialect

    def visit_header(self, header: List[str]) -> bool:
        """Validates the header fields in file. If the header doesn't have
        `<primary key>`, writes an error.

        Args:
          header: the list of header names

        Returns:
          True if required fields occur in the header, False otherwise
        """
        if self.__pk_field not in header:
            self.__error_writer.write(missing_field_error(self.__pk_field))
            return False

        self.__header = header

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Validates a row from the CSV file.

        If the row doesn't have `<primary key>`, writes an error.

        Args:
          row: the dictionary from the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if required fields occur in the row, False otherwise
        """
        if self.__pk_field not in row or row[self.__pk_field] == '':
            self.__error_writer.write(
                empty_field_error(self.__pk_field, line_num))
            return False

        return True


def read_first_data_row(input_file: TextIO, error_writer: ErrorWriter,
                        visitor: FormQCCSVVisitor) -> Optional[Dict[str, Any]]:
    """Reads CSV file and validates the header. Sets the CSV dialect for the
    visitor by sniffing a data sample.

    Args:
        input_file: the input stream for the CSV file
        error_writer: the ErrorWriter for the input file
        visitor: the visitor

    Returns:
        Returns first data row as a dict if no errors, else None
    """
    sniffer = Sniffer()
    csv_sample = input_file.read(1024)
    if not csv_sample:
        error_writer.write(empty_file_error())
        return None

    try:
        if not sniffer.has_header(csv_sample):
            error_writer.write(missing_header_error())
            return None

        detected_dialect = sniffer.sniff(csv_sample, delimiters=',')

        input_file.seek(0)
        reader = DictReader(input_file, dialect=detected_dialect)
    except Error as error:
        error_writer.write(malformed_file_error(str(error)))
        return None

    assert reader.fieldnames, "File has header, reader should have fieldnames"

    # check for required fields in the header
    if not visitor.visit_header(list(reader.fieldnames)):
        return None

    first_row = next(reader)
    visitor.dialect = detected_dialect  # type: ignore
    input_file.seek(0)

    return first_row
