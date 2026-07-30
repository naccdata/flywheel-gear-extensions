"""Defines two-phase batch Gather Form Data process."""

import logging
from csv import DictReader
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


def run(
    *,
    request_file: TextIO,
    proxy: FlywheelProxy,
    study_id: str,
    project_names: list[str],
    modules: set[str],
    info_paths: list[str],
    error_writer: ErrorWriter,
    batch_size: int = 100,
    reload_workers: int = 10,
    formver_split: bool = False,
) -> tuple[bool, list[ModuleDataGatherer]]:
    """Runs the two-phase gather form data process.

    Phase 1: Read CSV, validate NACCIDs, batch-resolve to subject IDs.
    Phase 2: Call gather_project_data on each module gatherer.

    Args:
        request_file: the data request file (open text stream)
        proxy: the Flywheel proxy
        study_id: the study ID
        project_names: list of project names to search
        modules: set of module names to gather
        info_paths: info paths for form data extraction
        error_writer: collects per-NACCID errors
        batch_size: max NACCIDs per OR-list query batch
        reload_workers: concurrent threads for file metadata reload
        formver_split: whether to split output by form version

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
    project_matcher = create_project_matcher(study_id, project_names)
    all_projects = proxy.find_projects_with_pattern(
        "|".join(project_names + [f"{name}-{study_id}" for name in project_names])
    )
    project_ids = [p.id for p in all_projects if project_matcher.match(p.label)]

    # --- Phase 1: Batch resolve NACCIDs to subjects ---
    deduplicated_naccids = list(set(valid_naccids))

    all_subjects = []
    for project_id in project_ids:
        subjects = proxy.find_subjects_by_labels(
            labels=deduplicated_naccids,
            project_id=project_id,
            batch_size=batch_size,
        )
        all_subjects.extend(subjects)

    # --- Phase 1: Error attribution for unresolved NACCIDs ---
    resolved_labels = {subject.label for subject in all_subjects}
    unresolved = set(deduplicated_naccids) - resolved_labels

    expected_studies = {study_id, "adrc"}
    for naccid in unresolved:
        error_writer.write(
            FileError(
                error_code="no-participant",  # pyright: ignore[reportCallIssue]
                error_type="error",  # pyright: ignore[reportCallIssue]
                location=CSVLocation(
                    line=naccid_line_map[naccid], column_name="naccid"
                ),
                message=(
                    f"no participant {naccid} with data for "
                    f"{','.join(expected_studies)}"
                ),
            )
        )
        has_errors = True

    # --- Phase 2: Gather data using resolved subject IDs ---
    subject_ids = [subject.id for subject in all_subjects]

    data_gatherers: list[ModuleDataGatherer] = []
    for module_name in modules:
        gatherer = ModuleDataGatherer(
            proxy=proxy,
            module_name=module_name,
            info_paths=info_paths,
            split_by_formver=formver_split,
        )
        if subject_ids:
            gatherer.gather_project_data(
                subject_ids=subject_ids,
                batch_size=batch_size,
                reload_workers=reload_workers,
            )
        data_gatherers.append(gatherer)

    success = not has_errors
    return (success, data_gatherers)
