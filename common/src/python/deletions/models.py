"""Data models for form deletion requests."""

from datetime import datetime
from typing import Optional

from nacc_common.form_dates import DATE_PATTERN
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from serialization.case import kebab_case


class DeleteRequest(BaseModel):
    """Class to represent a form visit delete request."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    ptid: str
    module: str
    visitdate: str = Field(pattern=DATE_PATTERN)
    visitnum: Optional[str] = None
    timestamp: datetime
    requested_by: str
