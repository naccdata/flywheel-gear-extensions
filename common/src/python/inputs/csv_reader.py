"""Methods to read and process a CSV file using a row visitor."""

import abc
from abc import ABC, abstractmethod
from csv import DictReader, Error, Sniffer
from typing import Any, Dict, List, Optional, TextIO

from outputs.errors import (ErrorWriter, empty_file_error,
                            malformed_file_error, missing_header_error)


class CSVVisitor(ABC):
    """Abstract class for a visitor for row in a CSV file."""

    @abstractmethod
    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for a row (per DictReader).

        Args:
          row: the dictionary for a row from a CSV file
        Returns:
          True if an error was encountered, False otherwise
        """
        return False

    @abstractmethod
    def visit_header(self, header: List[str]) -> bool:
        """Add the header.

        Args:
          header: list of header names
        Returns:
          True if the header is missing any required fields, False otherwise
        """
        return False


def read_csv(input_file: TextIO, error_writer: ErrorWriter,
             visitor: CSVVisitor) -> bool:
    """Reads CSV file and applies the visitor to each row.

    Args:
      input_file: the input stream for the CSV file
      error_writer: the ErrorWriter for the input file
      visitor: the visitor
    Returns:
      True if the input file has an error, False otherwise
    """
    sniffer = Sniffer()
    csv_sample = input_file.read(1024)
    if not csv_sample:
        error_writer.write(empty_file_error())
        return True

    try:
        has_header = sniffer.has_header(csv_sample)
    except Error as error:
        error_writer.write(malformed_file_error(str(error)))
        return True

    if not has_header:
        error_writer.write(missing_header_error())
        return True

    input_file.seek(0)
    detected_dialect = sniffer.sniff(csv_sample, delimiters=',')
    reader = DictReader(input_file, dialect=detected_dialect)
    assert reader.fieldnames, "File has header, reader should have fieldnames"

    error_found = visitor.visit_header(list(reader.fieldnames))
    if error_found:
        return True

    error_found = False
    for record in reader:
        error_in_row = visitor.visit_row(record, line_num=reader.line_num)
        error_found = error_in_row or error_found

    return error_found


# pylint: disable=(too-few-public-methods)
class RowValidator(abc.ABC):
    """Abstract class for a RowValidator."""

    @abc.abstractmethod
    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks the row passes the validation criteria of the implementing
        class.

        Args:
            row: the dictionary for the input row
        Returns:
            True if the validator check is true, False otherwise.
        """


# pylint: disable=(too-few-public-methods)
class AggregateRowValidator(RowValidator):
    """Row validator for running more than one validator."""

    def __init__(self,
                 validators: Optional[List[RowValidator]] = None) -> None:
        if validators:
            self.__validators = validators
        else:
            self.__validators = []

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks the row against each of the validators.

        Args:
            row: the dictionary for the input row
        Returns:
            True if all the validator checks are true, False otherwise
        """
        for validator in self.__validators:
            if not validator.check(row, line_number):
                return False

        return True
