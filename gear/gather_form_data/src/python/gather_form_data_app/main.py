"""Defines Gather Form Data."""

import logging
from typing import TextIO

from data_requests.data_request import (
    DataRequestMatch,
    DataRequestVisitor,
    ModuleDataGatherer,
)
from inputs.csv_reader import read_csv
from outputs.error_writer import ErrorWriter
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
        """Filter to valid module set and raise if none remain."""
        valid = {"UDS", "FTLD", "LBD"}
        filtered = v & valid
        if not filtered:
            raise ValueError(f"no valid modules specified; allowed values are {valid}")
        return filtered


def run(
    *,
    request_file: TextIO,
    request_visitor: DataRequestVisitor,
    error_writer: ErrorWriter,
):
    """Runs the Gather Form Data process, which reads individual participant
    request from the request file, applies the visitor to each to gather data
    for each form module.

    The error writer collects errors/warnings encountered while reading the
    request file.

    Args:
        request_file: the data request file
        request_visitor: the visitor
        error_writer: the error writer
    """
    return read_csv(
        input_file=request_file,
        error_writer=error_writer,
        visitor=request_visitor,
    )


def run_project_mode(
    *,
    requests: list[DataRequestMatch],
    gatherers: list[ModuleDataGatherer],
) -> bool:
    """Orchestrates per-subject data gathering for project mode.

    Applies each gatherer to each request. Logs warnings for failures
    and continues processing all subjects.

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
            except Exception as error:
                log.warning(
                    "Error gathering data for subject %s, module %s: %s",
                    request.naccid,
                    gatherer.module_name,
                    str(error),
                )

    return True
