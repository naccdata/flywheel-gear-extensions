"""Defines loni_csv_metadata_processor."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import (CSVDataModel,
                                                                  CSVRecord)
from loni_csv_metadata_processor_app.data_model.processor_output import \
    ProcessorOutput
from loni_csv_metadata_processor_app.processors.base_processor import \
    BaseProcessor
from loni_csv_metadata_processor_app.processors.final_processor import \
    FinalStatusProcessor
from loni_csv_metadata_processor_app.processors.qc_processor import QCProcessor
from loni_csv_metadata_processor_app.processors.scan_type_processor import \
    ScanTypeProcessor

log = logging.getLogger(__name__)


class CSVMetadataProcessor:
    """Main processor for CSV metadata."""

    def __init__(
        self,
    ):
        """
        Initialize the CSV metadata processor.
        """
        self.processors: List[BaseProcessor] = []
        self.file_tagger = None

        # Initialize processors
        self._initialize_processors()

    def _initialize_processors(self) -> None:
        """Initialize the processors for processing CSV data."""
        # Initialize individual processors
        # Easy to add or remove or modify what's getting checked/processed
        self.processors = [QCProcessor(), ScanTypeProcessor()]

        # Create a final status processor that will check all other processors
        self.final_processor = FinalStatusProcessor(processors=self.processors)

    def process_file(self, csv_path: Path) -> Dict[str, ProcessorOutput]:
        """
        Process a CSV file.

        Args:
            csv_path: Path to the CSV file to process.

        Returns:
            Dictionary with processing results, keyed by processor name.
        """

        # Load and validate CSV data
        data_model = CSVDataModel(csv_path)
        data_model.load()

        # Dictionary to store results from processors
        results: Dict[str, ProcessorOutput] = {}

        # Get the record from data_model
        record = data_model.get_record()

        # Process the data with each processor
        for processor in self.processors:
            output = processor.process(record)
            # Store results by processor class name
            results[processor.get_name()] = output

        # Finally, run the status processor to check all other processors
        final_output = self.final_processor.process(record)
        if final_output:
            results[self.final_processor.get_name()] = final_output

        return results


def run(
    input_path: Path,
):
    """Runs the loni_csv_metadata_processor process.

    Args:
        input_path: Path to the input CSV file.

    Returns:
        Dictionary with processing results.
    """
    # Default input path if none provided
    if input_path is None:
        input_path = Path("/flywheel/v0/input/file.csv")

    # Initialize processor
    processor = CSVMetadataProcessor()

    # Process the file and get results
    results = processor.process_file(input_path)

    # Results will be processed by process_output function in run.py

    # Log completion
    log.info(f"Processing complete with results for {len(results)} processors")

    return results
