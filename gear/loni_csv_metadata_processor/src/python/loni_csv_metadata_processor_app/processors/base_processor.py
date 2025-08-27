"""
Base processor defining the strategy interface for processing CSV data.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVRecord
from loni_csv_metadata_processor_app.data_model.processor_output import (
    ProcessorOutput, ProcessState)
from loni_csv_metadata_processor_app.processors.handlers.base_handler import \
    RecordHandler


class BaseProcessor(ABC):
    """
    Abstract base class for all processors that operate on CSV data.
    Implements the Strategy Pattern.
    """

    def __init__(self):
        """Initialize the processor."""
        self.state = ProcessState.UNKNOWN
        self.handlers: List[RecordHandler] = []

    def get_state(self) -> ProcessState:
        """
        Get the current state of the processor.

        Returns:
            The current state (PASS, FAIL, or UNKNOWN).
        """
        return self.state

    def set_state(self, state: ProcessState) -> None:
        """
        Set the state of the processor.

        Args:
            state: The state to set.
        """
        self.state = state

    def get_name(self) -> str:
        """
        Get the name of the processor.

        Returns:
            The name of the processor class.
        """
        return self.__class__.__name__

    def _get_handler_for_record(self, record: CSVRecord) -> Optional[RecordHandler]:
        """
        Get the appropriate handler for the given record type.

        Args:
            record: The record to find a handler for.

        Returns:
            The appropriate handler or None if no suitable handler is found.
        """
        for handler in self.handlers:
            if handler.can_handle(record):
                return handler

        return None

    @abstractmethod
    def process(self, record: CSVRecord) -> ProcessorOutput:
        """
        Process the CSV record according to the specific strategy.

        Args:
            record: The CSV record to process.

        Returns:
            ProcessorOutput containing status and value, or None if processing failed.
        """
        pass
