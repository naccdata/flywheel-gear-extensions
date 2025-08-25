"""
Processor for determining scan type.
"""
from typing import Dict, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVDataModel
from loni_csv_metadata_processor_app.utils.file_tagger import FileTagger
from loni_csv_metadata_processor_app.processors.base_processor import BaseProcessor


class ScanTypeProcessor(BaseProcessor):
    """
    Processor that determines the type of scan performed.
    """
    
    def __init__(self, file_tagger: FileTagger, scan_type_keywords: Dict[str, str] = None):
        """
        Initialize the scan type processor.
        
        Args:
            file_tagger: Utility for tagging files.
            scan_type_keywords: Dictionary mapping keywords to scan types.
        """
        super().__init__(file_tagger)
        self.scan_type_keywords = scan_type_keywords or {}
    
    def process(self, data_model: CSVDataModel) -> Dict[str, str]:
        """
        Process the CSV data to determine scan types.
        
        Args:
            data_model: The CSV data model to process.
            
        Returns:
            Dictionary mapping record IDs to determined scan types.
        """
        results = {}
        
        # Placeholder for actual scan type determination logic
        # This would analyze each record to determine the scan type
        
        # Placeholder for tagging based on scan type
        # self.file_tagger.tag_file(...)
        
        return results
    
    def _determine_scan_type(self, record_data: Dict) -> Optional[str]:
        """
        Helper method to determine scan type from record data.
        
        Args:
            record_data: Data from a single CSV record.
            
        Returns:
            Determined scan type or None if undetermined.
        """
        pass
