"""Data models for form deletion requests."""

import re
from datetime import datetime
from typing import List, Optional

from nacc_common.error_models import FileError, QCStatus
from nacc_common.form_dates import DATE_PATTERN
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field, field_validator
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

    @field_validator("ptid", mode="before")
    def clean_ptid(cls, value: str) -> str:
        return value.strip().lstrip("0")


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
    job_id: Optional[str] = None

    def get_deleted_visits_list(self) -> Optional[str]:
        """Returns the list of deleted visits as a newline-joined string."""

        if not self.delete_response.deleted:
            return None

        # Log file name format: {ptid}_{YYYY-MM-DD}[_{visitnum}]_{module}_qc-status.log
        # Anchor on the fixed-format date to handle a ptid that contains "_".

        pattern = re.compile(
            r"^(.+)_(\d{4}-\d{2}-\d{2})_(?:(\w+)_)?(\w+)_qc-status\.log$"
        )

        visits = []

        for logfile in self.delete_response.deleted.logs:
            match = pattern.match(logfile)
            if not match:
                continue
            ptid, date, visitnum, module = match.groups()
            visit_str = f"PTID={ptid}, Module={module.upper()}, Date={date}"
            if visitnum:
                visit_str += f", Visit Number={visitnum}"
            visits.append(visit_str)

        return "\n".join(visits) if visits else None
