"""Defines two-phase batch Gather Form Data process."""

import logging
from csv import DictReader
from dataclasses import dataclass, field
from typing import TextIO

from data_requests.data_request import (
    DataRequest,
    ModuleDataGatherer,
    create_project_matcher,
)
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from nacc_common.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error
from pydantic import ValidationError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatherConfig:
    """Configuration for the gather form data process.

    Groups study/project selection, module filtering, and performance-
    tuning parameters into a single structured object.
    """

    study_id: str
    project_names: list[str]
    modules: set[str]
    info_paths: list[str] = field(default_factory=lambda: ["forms.json"])
    batch_size: int = 100
    reload_workers: int = 10
    formver_split: bool = False


def run(
    *,
    request_file: TextIO,
    proxy: FlywheelProxy,
    config: GatherConfig,
    error_writer: ErrorWriter,
) -> tuple[bool, list[ModuleDataGatherer]]:
    """Runs the two-phase gather form data process.

    Phase 1: Read CSV, validate NACCIDs, batch-resolve to subject IDs.
    Phase 2: Call gather_project_data on each module gatherer.

    Args:
        request_file: the data request file (open text stream)
        proxy: the Flywheel proxy
        config: gather configuration (study, modules, performance tuning)
        error_writer: collects per-NACCID errors

    Returns:
        Tuple of (success, gatherers) where success is False if any
        NACCID failed validation or resolution, and gatherers contain
        the collected data.
    """
    # --- Phase 1: Read and validate NACCIDs ---
    valid_naccids: list[str] = []
    naccid_line_map: dict[str, int] = {}
    has_errors = False

    reader = DictReader(request_file)
    for line_num, row in enumerate(reader, start=1):
        try:
            request = DataRequest.model_validate(row)
            valid_naccids.append(request.naccid)
            if request.naccid not in naccid_line_map:
                naccid_line_map[request.naccid] = line_num
        except ValidationError as error:
            error_writer.write(malformed_file_error(str(error)))
            has_errors = True

    # --- Phase 1: Look up project IDs ---
    project_matcher = create_project_matcher(config.study_id, config.project_names)
    all_projects = proxy.find_projects_with_pattern(
        "|".join(
            config.project_names
            + [f"{name}-{config.study_id}" for name in config.project_names]
        )
    )
    project_ids = [p.id for p in all_projects if project_matcher.match(p.label)]

    # --- Phase 1: Batch resolve NACCIDs to subjects ---
    deduplicated_naccids = list(set(valid_naccids))

    all_subjects = []
    for project_id in project_ids:
        subjects = proxy.find_subjects_by_labels(
            labels=deduplicated_naccids,
            project_id=project_id,
            batch_size=config.batch_size,
        )
        all_subjects.extend(subjects)

    # --- Phase 1: Error attribution for unresolved NACCIDs ---
    resolved_labels = {subject.label for subject in all_subjects}
    unresolved = set(deduplicated_naccids) - resolved_labels

    # Coenrollment: affiliated studies (e.g. allftd) share subjects with adrc,
    # so "adrc" is always included in the expected set for error messaging.
    expected_studies = {config.study_id, "adrc"}
    for naccid in unresolved:
        # pyright doesn't understand Pydantic's populate_by_name=True config,
        # which allows construction using the Python field name (error_code,
        # error_type) instead of the alias (code, type).
        error_writer.write(
            FileError(
                error_code="no-participant",  # pyright: ignore[reportCallIssue]
                error_type="warning",  # pyright: ignore[reportCallIssue]
                location=CSVLocation(
                    line=naccid_line_map[naccid], column_name="naccid"
                ),
                message=(
                    f"no participant {naccid} with data for "
                    f"{','.join(expected_studies)}"
                ),
            )
        )

    # --- Phase 2: Gather data using resolved subject IDs ---
    subject_ids = [subject.id for subject in all_subjects]

    data_gatherers: list[ModuleDataGatherer] = []
    for module_name in config.modules:
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name=module_name,
            info_paths=config.info_paths,
            split_by_formver=config.formver_split,
        )
        if subject_ids:
            gatherer.gather_project_data(
                subject_ids=subject_ids,
                batch_size=config.batch_size,
                reload_workers=config.reload_workers,
            )
        data_gatherers.append(gatherer)

    success = not has_errors
    return (success, data_gatherers)
