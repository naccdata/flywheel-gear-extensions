"""Defines a data model for visit event logging.

Supports tracking:
- visit data submission
- visit data deletion
- visit data passes QC
- visit data did not pass QC

Note: processes do not support issuing an explicit QC failure event.
"""

from datetime import date, datetime
from typing import Literal

from identifiers.model import PTID_PATTERN
from pydantic import BaseModel, Field

VisitEventType = Literal["submit", "delete", "not-pass-qc", "pass-qc"]


class VisitEvent(BaseModel):
    action: VisitEventType
    pipeline_adcid: int
    project_label: str
    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)
    visit_date: date
    visit_number: str
    timestamp: datetime
