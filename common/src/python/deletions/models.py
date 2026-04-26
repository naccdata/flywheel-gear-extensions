"""Data models for form deletion requests."""

from datetime import datetime
from typing import List, Optional

from nacc_common.error_models import FileError, QCStatus
from nacc_common.form_dates import DATE_PATTERN
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from serialization.case import kebab_case


class DeleteRequest(BaseModel):
    """Model to represent a form visit delete request."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    ptid: str
    module: str
    visitdate: str = Field(pattern=DATE_PATTERN)
    visitnum: Optional[str] = None
    timestamp: datetime
    requested_by: str


class DeletedItems(BaseModel):
    """Model to represent items deleted while processing a delete request."""

    logs: List[str] = Field(default_factory=list)
    subjects: List[str] = Field(default_factory=list)
    sessions: List[str] = Field(default_factory=list)
    acquisitions: List[str] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    """Model to represent a response for delete request.

    Located within file.info.delete_response
    """

    errors: Optional[List[FileError]] = None
    deleted: Optional[DeletedItems] = None
    state: QCStatus


class DeleteInfoModel(BaseModel):
    """Model for storing delete request success/failure in request file custom
    info.

    Located within file.info
    """

    delete_response: DeleteResponse
    processed_timestamp: Optional[datetime] = None
