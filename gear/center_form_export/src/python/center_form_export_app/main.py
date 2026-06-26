"""Defines Center Form Export business logic."""

import logging

from data_requests.data_request import (
    DataRequestMatch,
    ModuleDataError,
    ModuleDataGatherer,
)
from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


class ProjectModeConfig(BaseModel):
    """Validated configuration for project mode execution."""

    group_id: str
    project_name: str
    modules: set[str]
    info_paths: list[str]
    study_id: str

    @field_validator("group_id", "project_name")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        """Reject blank or whitespace-only strings."""
        if not v.strip():
            raise ValueError("must not be empty or whitespace-only")
        return v.strip()

    @field_validator("modules")
    @classmethod
    def must_have_valid_modules(cls, v: set[str]) -> set[str]:
        """Reject empty or whitespace-only module sets."""
        filtered = {module.strip() for module in v if module.strip()}
        if not filtered:
            raise ValueError("at least one module must be specified")
        return filtered


def run_project_mode(
    *,
    requests: list[DataRequestMatch],
    gatherers: list[ModuleDataGatherer],
) -> bool:
    """Orchestrates per-subject data gathering for project mode.

    Applies each gatherer to each request. Logs warnings for data access
    failures and continues processing all subjects.

    Args:
        requests: DataRequestMatch objects for each subject
        gatherers: ModuleDataGatherer instances for configured modules

    Returns:
        True if processing completed (even with individual failures)
    """
    for request in requests:
        for gatherer in gatherers:
            try:
                gatherer.gather_request_data(request)
            except ModuleDataError as error:
                log.warning(
                    "Error gathering data for subject %s, module %s: %s",
                    request.naccid,
                    gatherer.module_name,
                    str(error),
                )

    return True
