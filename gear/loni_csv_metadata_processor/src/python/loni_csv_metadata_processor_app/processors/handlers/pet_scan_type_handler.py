"""
PET record handler for scan type processing.
"""
from typing import Dict, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import (CSVRecord,
                                                                  CSVType)
from loni_csv_metadata_processor_app.processors.handlers.base_handler import \
    RecordHandler


class PETScanTypeHandler(RecordHandler):
    """
    Handler for processing PET records in the scan type processor.
    """

    def __init__(self, scan_type_keywords: Optional[Dict[str, str]] = None):
        """
        Initialize the PET scan type handler.

        Args:
            scan_type_keywords: Dictionary mapping keywords to scan types.
        """
        self.scan_type_keywords = scan_type_keywords or {}

    def can_handle(self, record: CSVRecord) -> bool:
        """
        Check if this handler can process the given record.

        Args:
            record: The CSV record to check.

        Returns:
            True if the record is a PET record, False otherwise.
        """
        return record.record_type == CSVType.PET

    def handle(self, record: CSVRecord) -> Optional[Dict]:
        """
        Process the PET record to determine scan type.

        Args:
            record: The PET record to process.

        Returns:
            Dictionary with scan type results or None if processing failed.
        """
        # PET-specific logic to determine scan type
        # This could analyze field_b1, field_b2, etc. which are specific to PET

        # Example implementation outline:
        if hasattr(record, "field_b1") and record.field_b1:
            # Logic specific to PET records
            scan_type = "pet_default_type"
            return {"scan_type": scan_type, "tracer_type": "FDG"}

        return None
