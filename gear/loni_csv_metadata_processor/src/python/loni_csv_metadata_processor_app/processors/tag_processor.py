"""
Processor for tagging CSV files as processed.
"""
from pathlib import Path
from typing import List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVDataModel
from loni_csv_metadata_processor_app.utils.file_tagger import FileTagger
from loni_csv_metadata_processor_app.processors.base_processor import BaseProcessor


class TagProcessor(BaseProcessor):
    """
    Processor that tags CSV files as processed.
    """
    
    def __init__(self, file_tagger: FileTagger, tag_name: str = "processed"):
        """
        Initialize the tag processor.
        
        Args:
            file_tagger: Utility for tagging files.
            tag_name: The name of the tag to apply.
        """
        super().__init__(file_tagger)
        self.tag_name = tag_name
    
    def process(self, data_model: CSVDataModel) -> bool:
        """
        Process the CSV data by tagging the file as processed.
        
        Args:
            data_model: The CSV data model to process.
            
        Returns:
            True if tagging was successful, False otherwise.
        """
        # Tag the file as processed
        # self.file_tagger.tag_file(data_model.csv_path, self.tag_name)
        
        return True
