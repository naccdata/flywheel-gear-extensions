"""Methods to read and process a CSV file using a row visitor."""

import abc
import logging
from abc import ABC, abstractmethod
from csv import DictReader
from typing import Any, Callable, Dict, List, Optional, Sequence, TextIO

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


VisitorStrategyType = Callable[[dict[str, Any], int], bool]
VisitorStrategyBuilderType = Callable[[Sequence[CSVVisitor]], VisitorStrategyType]


def short_circuit_strategy(visitors: Sequence[CSVVisitor]) -> VisitorStrategyType:
    """Returns a function determining the strategy for executing visit_row
    using the visitors in the sequence.

    Builds a short-circuiting strategy, where execution stops at the first
    visitor that returns False.

    Args:
      visitors: the visitors
    Returns:
      the short-circuiting strategy function
    """

    def strategy(row: dict[str, Any], line_num: int) -> bool:
        return all(visitor.visit_row(row, line_num) for visitor in visitors)

    return strategy


def visit_all_strategy(visitors: Sequence[CSVVisitor]) -> VisitorStrategyType:
    """Returns a function determining a strategy for executing visit_row using
    the visitors in the sequence.

    Args:
      visitors: the visitors
    Returns:
      the visit-all strategy function
    """

    def strategy(row: dict[str, Any], line_num: int) -> bool:
        """Execution strategy that calls all visitors regardless of
        failures."""
        results = []
        for visitor in visitors:
            try:
                result = visitor.visit_row(row, line_num)
                results.append(result)
            except Exception as error:
                log.error(
                    f"Error in visitor {visitor.__class__.__name__} "
                    f"for row {line_num}: {error}"
                )
                results.append(False)
        return all(results)

    return strategy


class AggregateCSVVisitor(CSVVisitor):
    """Aggregates CSV visitors with configurable execution strategies.

    Uses dependency injection to allow different execution strategies:
    - short_circuit_strategy: Stops execution on first visitor failure (default)
    - visit_all_strategy: Calls all visitors regardless of individual failures
    """

    def __init__(
        self,
        visitors: Sequence[CSVVisitor],
        strategy_builder: VisitorStrategyBuilderType = short_circuit_strategy,
    ) -> None:
        """Initialize aggregate CSV visitor.

        Args:
            visitors: Sequence of visitors to coordinate
            strategy_builder: Function that builds the execution strategy for visit_row.
                            Defaults to short_circuit_strategy (stops on first failure).
                            Use visit_all_strategy to call all visitors regardless
                            of failures.
        """
        self.__visitors = visitors
        self.__strategy = strategy_builder(visitors)

    def visit_header(self, header: List[str]) -> bool:
        """Visits headers with each of the visitors.

        Args:
          header: list of header names
        Returns:
          True if all of the visitors return true for the header
        """
        return all(visitor.visit_header(header) for visitor in self.__visitors)

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visits row with each of the visitors using the configured strategy.

        Args:
          row: the dictionary for a row of a CSV file
          line_num: the line number of the row
        Returns:
          True if the execution strategy determines success, False otherwise.
          Behavior depends on the strategy_builder used during initialization.
        """
        return self.__strategy(row, line_num)

    def valid_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Checks that the row is valid.

        Args:
          row: the dictionary for a row
          line_num: the line number for the row
        Returns:
          True if all of the visitors return True. False, otherwise.
        """
        return all(visitor.valid_row(row, line_num) for visitor in self.__visitors)


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
