"""
Model for processor output data.
"""
from enum import Enum, auto
from typing import Any, Optional
from pydantic import BaseModel


class ProcessorOutput(BaseModel):
    """
    Output model for processors.
    
    Attributes:
        status: 'pass' or 'fail' status of the processing
        value: Any value to be used as a tag, or None
    """
    status: str  # 'pass', 'fail', or other status values
    value: Optional[Any] = None


class ProcessState(Enum):
    """
    Enum representing the state of a processor's execution.
    """
    PASS = auto()
    FAIL = auto()
    UNKNOWN = auto()