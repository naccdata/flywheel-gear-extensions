"""
Base handler interface for type-specific processing logic.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVRecord


class RecordHandler(ABC):
    """
    Abstract base class for record type-specific handlers.
    """

    @abstractmethod
    def can_handle(self, record: CSVRecord) -> bool:
        """
        Determine if this handler can process the given record type.
        
        Args:
            record: The CSV record to check.
            
        Returns:
            True if this handler can process the record, False otherwise.
        """
        pass
        
    @abstractmethod
    def handle(self, record: CSVRecord) -> Optional[Dict]:
        """
        Process the record according to its specific type requirements.
        
        Args:
            record: The CSV record to process.
            
        Returns:
            Dictionary with processing results or None if processing failed.
        """
        pass