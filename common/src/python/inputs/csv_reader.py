"""Methods to read and process a CSV file using a row visitor."""

import abc
import logging
from abc import ABC, abstractmethod
from csv import DictReader
from typing import Any, Dict, List, Optional, TextIO

from outputs.error_writer import ErrorWriter, ListErrorWriter
from outputs.errors import (
    empty_file_error,
    missing_header_error,
    partially_failed_file_error,
)
from utils.snakecase import snakecase

log = logging.getLogger(__name__)


class CSVVisitor(ABC):
    """Abstract class for a visitor for row in a CSV file."""

    @abstractmethod
    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for a row (per DictReader).

        Args:
          row: the dictionary for a row from a CSV file
          line_num: the line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        return True

    @abstractmethod
    def visit_header(self, header: List[str]) -> bool:
        """Add the header.

        Args:
          header: list of header names
        Returns:
          True if the header has all required fields, False otherwise
        """
        return True

    def valid_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Checks that the row is valid.

        Override this method if there is a row condition that requires stopping
        processing of the file.

        Args:
          row: the dictionary for a row
          line_num: the line number of the row
        Returns:
          True if the row is valid. False, otherwise.
        """
        return True


def read_csv(
    *,
    input_file: TextIO,
    error_writer: ErrorWriter,
    visitor: CSVVisitor,
    delimiter: str = ",",
    limit: Optional[int] = None,
    clear_errors: Optional[bool] = False,
    preserve_case: bool = True,
) -> bool:
    """Reads CSV file and applies the visitor to each row.

    Args:
      input_file: the input stream for the CSV file
      error_writer: the ErrorWriter for the input file
      visitor: the visitor
      delimiter: expected delimiter for the CSV
      limit: maximum number of lines to read (excluding header)
      clear_errors: clear the accumulated error metadata
      preserve_case: Whether or not to preserve case while reading
        the CSV header keys. If false, will convert all headers
        to lowercase and replace spaces with underscores

    Returns:
      True if the input file was processed without error, False otherwise
    """
    csv_sample = input_file.read(1024)
    if not csv_sample:
        error_writer.write(empty_file_error())
        return False

    input_file.seek(0)

    reader = DictReader(input_file, delimiter=delimiter)
    if not reader.fieldnames:
        error_writer.write(missing_header_error())
        return False

    # visitor should handle errors for invalid headers/rows
    headers = list(reader.fieldnames)
    if not preserve_case:
        headers = [snakecase(x.strip()) for x in headers]

    success = visitor.visit_header(headers)
    if not success:
        return False

    for count, record in enumerate(reader):
        if not preserve_case:
            record = {snakecase(key.strip()): value for key, value in record.items()}

        if not visitor.valid_row(record, line_num=count + 1):
            success = False
            break

        row_success = visitor.visit_row(record, line_num=count + 1)
        success = row_success and success
        if limit and count >= limit:
            break

    if not success and clear_errors and isinstance(error_writer, ListErrorWriter):
        error_writer.clear()
        error_writer.write(partially_failed_file_error())

    return success


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

    def __init__(self, validators: Optional[List[RowValidator]] = None) -> None:
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
        return all(validator.check(row, line_number) for validator in self.__validators)
