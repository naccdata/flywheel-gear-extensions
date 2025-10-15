"""Defines a data model for visit event logging.

Supports tracking:
- visit data submission
- visit data deletion
- visit data passes QC
- visit data did not pass QC

Note: processes do not support issuing an explicit QC failure event.
"""

from datetime import date, datetime
from typing import Literal, Optional, Self

from identifiers.model import PTID_PATTERN
from keys.types import DatatypeNameType
from nacc_common.module_types import ModuleName
from pydantic import BaseModel, Field, model_validator

VisitEventType = Literal["submit", "delete", "not-pass-qc", "pass-qc"]


class VisitEvent(BaseModel):
    action: VisitEventType
    pipeline_adcid: int
    project_label: str
    center_label: str
    gear_name: str
    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)
    visit_date: date
    visit_number: str
    datatype: DatatypeNameType
    module: Optional[ModuleName] = None
    timestamp: datetime

    @model_validator(mode="after")
    def validate_module(self) -> Self:
        if self.datatype != "form" and self.module is not None:
            raise ValueError(
                f"Visit event has datatype {self.datatype}, "
                "but has form module {self.module}"
            )

        if self.datatype == "form" and self.module is None:
            raise ValueError("Expected module name for form datatype")

        return self
