"""
Processor for determining if a scan passed or failed QC.
"""
from typing import Dict, List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVRecord
from loni_csv_metadata_processor_app.data_model.processor_output import ProcessState, ProcessorOutput
from loni_csv_metadata_processor_app.processors.base_processor import BaseProcessor
from loni_csv_metadata_processor_app.processors.handlers.base_handler import RecordHandler
from loni_csv_metadata_processor_app.processors.handlers.mri_qc_handler import MRIQCHandler
from loni_csv_metadata_processor_app.processors.handlers.pet_qc_handler import PETQCHandler


class QCProcessor(BaseProcessor):
    """
    Processor that determines if scans passed or failed QC.
    Uses type-specific handlers to implement record type-specific logic.
    """
    
    def __init__(
        self, qc_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        Initialize the QC processor.
        
        Args:
            qc_thresholds: Dictionary mapping QC metric names to threshold values.
        """
        super().__init__()
        self.qc_thresholds = qc_thresholds or {}
        
        # Initialize handlers for different record types
        self.handlers: List[RecordHandler] = [
            MRIQCHandler(qc_thresholds),
            PETQCHandler(qc_thresholds)
        ]
    
    def process(self, record: CSVRecord) -> ProcessorOutput:
        """
        Process the CSV record to determine QC status.
        Uses appropriate handler based on the record type.
        
        Args:
            record: The CSV record to process.
            
        Returns:
            ProcessorOutput with status and value, or None if processing failed.
        """
        try:
            if not record:
                self.set_state(ProcessState.FAIL)
                return ProcessorOutput(status="fail", value=None)
                
            # Find the appropriate handler for this record type
            handler = self._get_handler_for_record(record)
            
            if handler:
                # Process the record with the type-specific handler
                qc_result = handler.handle(record)
                
                if qc_result and qc_result.get('qc_status') == "pass":
                    self.set_state(ProcessState.PASS)
                    return ProcessorOutput(status="pass", value=qc_result)
                else:
                    self.set_state(ProcessState.FAIL)
                    return ProcessorOutput(status="fail", value=qc_result)
            else:
                # No suitable handler found for this record type
                self.set_state(ProcessState.FAIL)
                return ProcessorOutput(
                    status="fail",
                    value={"error": f"Unsupported record type: {record.record_type}"}
                )
            
        except Exception as e:
            print(f"Error in QCProcessor: {e}")
            self.set_state(ProcessState.FAIL)
            return ProcessorOutput(status="fail", value=None)
