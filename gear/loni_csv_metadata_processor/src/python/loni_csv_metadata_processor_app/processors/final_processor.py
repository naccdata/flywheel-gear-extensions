"""
Processor for determining final status of CSV file processing.
"""
import contextlib
from typing import List, Optional

from loni_csv_metadata_processor_app.data_model.csv_model import CSVRecord
from loni_csv_metadata_processor_app.data_model.processor_output import ProcessState, ProcessorOutput
from loni_csv_metadata_processor_app.processors.base_processor import (
    BaseProcessor
)


class FinalStatusProcessor(BaseProcessor):
    """
    Special processor that checks the status of all other processors and
    determines the overall processing status based on the collective result.
    """
    
    def __init__(
        self,
        processors: Optional[List[BaseProcessor]] = None,
    ):
        """
        Initialize the status processor.
        
        Args:
            processors: List of processors to check status from.
        """
        super().__init__()
        self.processors = processors or []

    def set_processors(self, processors: List[BaseProcessor]) -> None:
        """
        Set the list of processors to check.
        
        Args:
            processors: List of processors to check status from.
        """
        self.processors = processors
    
    def process(self, record: CSVRecord) -> ProcessorOutput:
        """
        Check the status of all processors and determine overall status.
        
        Args:
            record: The CSV record (not used by this processor as it only checks other processors).
            
        Returns:
            ProcessorOutput with overall status and value.
        """
        try:
            # Default state to PASS (optimistic)
            self.set_state(ProcessState.PASS)
            
            # Check each processor's state
            for processor in self.processors:
                state = processor.get_state()
                
                # If any processor failed, mark overall state as failed
                if state in [ProcessState.FAIL, ProcessState.UNKNOWN]:
                    self.set_state(ProcessState.FAIL)
                    break
            
            # Determine overall status
            if self.state == ProcessState.PASS:
                status = "pass"
                value = True  # Processed successfully
            else:
                status = "fail"
                value = False  # Processing failed
                
            # Return the processor output
            return ProcessorOutput(status=status, value=value)
            
        except Exception as e:
            print(f"Error in FinalStatusProcessor: {e}")
            self.set_state(ProcessState.FAIL)
            return ProcessorOutput(status="fail", value=False)

