from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from identifiers.model import PTID_PATTERN

VisitEventType = Literal["create", "delete", "fail-qc", "pass-qc"]

class VisitEvent(BaseModel):
    action: VisitEventType
    pipeline_adcid: int
    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)
    timestamp: datetime
