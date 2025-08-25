"""
Base processor defining the strategy interface for processing CSV data.
"""
from abc import ABC, abstractmethod
from typing import Any

from loni_csv_metadata_processor_app.data_model.csv_model import CSVDataModel
from loni_csv_metadata_processor_app.utils.file_tagger import FileTagger


class BaseProcessor(ABC):
    """
    Abstract base class for all processors that operate on CSV data.
    Implements the Strategy Pattern.
    """
    
    def __init__(self, file_tagger: FileTagger):
        """
        Initialize the processor with a file tagger.
        
        Args:
            file_tagger: Utility for tagging files.
        """
        self.file_tagger = file_tagger
    
    @abstractmethod
    def process(self, data_model: CSVDataModel) -> Any:
        """
        Process the CSV data model according to the specific strategy.
        
        Args:
            data_model: The CSV data model to process.
            
        Returns:
            Processor-specific result.
        """
        pass
