"""Defines loni_csv_metadata_processor."""

import logging
from pathlib import Path
from typing import List, Optional

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

from loni_csv_metadata_processor_app.config.config import ApplicationConfig, load_config
from loni_csv_metadata_processor_app.data_model.csv_model import CSVDataModel
from loni_csv_metadata_processor_app.processors.base_processor import BaseProcessor
from loni_csv_metadata_processor_app.processors.qc_processor import QCProcessor
from loni_csv_metadata_processor_app.processors.scan_type_processor import ScanTypeProcessor
from loni_csv_metadata_processor_app.processors.tag_processor import TagProcessor
from loni_csv_metadata_processor_app.utils.file_tagger import FileTagger
from loni_csv_metadata_processor_app.utils.logger import setup_logger

log = logging.getLogger(__name__)


class CSVMetadataProcessor:
    """Main processor for CSV metadata."""
    
    def __init__(self, config: ApplicationConfig, file_tagger: FileTagger):
        """
        Initialize the CSV metadata processor.
        
        Args:
            config: Application configuration.
            file_tagger: Utility for tagging files.
        """
        self.config = config
        self.file_tagger = file_tagger
        self.processors: List[BaseProcessor] = []
        
        # Initialize processors
        self._initialize_processors()
    
    def _initialize_processors(self) -> None:
        """Initialize the processors for processing CSV data."""
        self.processors = [
            QCProcessor(self.file_tagger, self.config.qc_thresholds),
            ScanTypeProcessor(self.file_tagger, self.config.scan_type_keywords),
            TagProcessor(self.file_tagger, self.config.tag_name)
        ]
    
    def process_file(self, csv_path: Path) -> None:
        """
        Process a CSV file.
        
        Args:
            csv_path: Path to the CSV file to process.
        """
        # Load and validate CSV data
        data_model = CSVDataModel(csv_path)
        data_model.load()
        
        # Process the data with each processor
        for processor in self.processors:
            processor.process(data_model)


def run(*, proxy: FlywheelProxy, config_path: Optional[Path] = None):
    """Runs the loni_csv_metadata_processor process.

    Args:
        proxy: the proxy for the Flywheel instance
        config_path: Optional path to the configuration file.
    """
    # Set up logger
    logger = setup_logger("loni_csv_metadata_processor")
    
    # Load configuration
    config = load_config(config_path)
    
    # Initialize file tagger
    file_tagger = FileTagger()
    
    # Initialize and run processor
    processor = CSVMetadataProcessor(config, file_tagger)
    processor.process_file(config.input_path)
