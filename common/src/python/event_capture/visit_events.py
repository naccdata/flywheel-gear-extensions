"""Defines a data model for visit event logging.

Supports tracking:
- visit data submission
- visit data deletion
- visit data passes QC
- visit data did not pass QC

Note: processes do not support issuing an explicit QC failure event.
"""

from datetime import datetime
from typing import Literal, Optional, Self

from identifiers.model import PTID_PATTERN
from keys.types import DatatypeNameType
from pydantic import BaseModel, Field, field_validator, model_validator

VisitEventType = Literal["submit", "delete", "not-pass-qc", "pass-qc"]

# Visit Event Action constants
ACTION_SUBMIT = "submit"
ACTION_DELETE = "delete"
ACTION_NOT_PASS_QC = "not-pass-qc"
ACTION_PASS_QC = "pass-qc"


class VisitEvent(BaseModel):
    action: VisitEventType
    study: str = "adrc"
    pipeline_adcid: int
    project_label: str
    center_label: str
    gear_name: str
    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)
    visit_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    visit_number: Optional[str] = None
    datatype: DatatypeNameType
    module: Optional[str] = None
    packet: Optional[str] = None
    timestamp: datetime

    @field_validator("module")
    @classmethod
    def normalize_module(cls, v: Optional[str]) -> Optional[str]:
        """Normalize module to uppercase for canonical storage and matching.

        This ensures consistency with EventMatchKey matching logic and
        provides case-insensitive module handling throughout the system.

        Args:
            v: The module value

        Returns:
            Module normalized to uppercase, or None if input is None
        """
        return v.upper() if v else v

    # TODO: do we need validation for packet?
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
