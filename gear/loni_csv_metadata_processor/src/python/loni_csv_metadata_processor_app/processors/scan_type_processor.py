"""
Processor for determining scan type.
"""
from typing import Dict, List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVRecord
from loni_csv_metadata_processor_app.data_model.processor_output import (
    ProcessorOutput, ProcessState)
from loni_csv_metadata_processor_app.processors.base_processor import \
    BaseProcessor
from loni_csv_metadata_processor_app.processors.handlers.base_handler import \
    RecordHandler
from loni_csv_metadata_processor_app.processors.handlers.mri_scan_type_handler import \
    MRIScanTypeHandler
from loni_csv_metadata_processor_app.processors.handlers.pet_scan_type_handler import \
    PETScanTypeHandler


class ScanTypeProcessor(BaseProcessor):
    """
    Processor that determines the type of scan performed.
    Uses type-specific handlers to implement record type-specific logic.
    """

    def __init__(self, scan_type_keywords: Optional[Dict[str, str]] = None):
        """
        Initialize the scan type processor.

        Args:
            scan_type_keywords: Dictionary mapping keywords to scan types.
        """
        super().__init__()
        self.scan_type_keywords = scan_type_keywords or {}

        # Initialize handlers for different record types
        self.handlers: List[RecordHandler] = [
            MRIScanTypeHandler(scan_type_keywords),
            PETScanTypeHandler(scan_type_keywords),
        ]

    def process(self, record: CSVRecord) -> ProcessorOutput:
        """
        Process the CSV record to determine scan types.
        Uses appropriate handler based on the record type.

        Args:
            record: The CSV record to process.

        Returns:
            ProcessorOutput with status and scan type value, or None if processing failed.
        """
        try:
            if not record:
                self.set_state(ProcessState.FAIL)
                return ProcessorOutput(status="fail", value=None)

            # Find the appropriate handler for this record type
            handler = self._get_handler_for_record(record)

            if handler:
                # Process the record with the type-specific handler
                result = handler.handle(record)

                if result and result.get("scan_type"):
                    self.set_state(ProcessState.PASS)
                    return ProcessorOutput(status="pass", value=result)
                else:
                    self.set_state(ProcessState.FAIL)
                    return ProcessorOutput(status="fail", value=None)
            else:
                # No suitable handler found for this record type
                self.set_state(ProcessState.FAIL)
                return ProcessorOutput(
                    status="fail",
                    value={"error": f"Unsupported record type: {record.record_type}"},
                )

        except Exception as e:
            print(f"Error in ScanTypeProcessor: {e}")
            self.set_state(ProcessState.FAIL)
            return ProcessorOutput(status="fail", value=None)
