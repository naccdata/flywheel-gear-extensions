"""Core business logic for the dicom-qc-checker gear."""

import logging
from typing import Any

from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from nacc_common.error_models import GearTags

log = logging.getLogger(__name__)


def determine_qc_status(
    dicom_qc: dict[str, Any],
) -> tuple[str, list[str]]:
    """Determine overall QC status from dicom-qc metadata.

    Evaluates check result entries in the DICOM QC metadata dictionary,
    excluding the job_info entry and any non-check entries.

    Args:
        dicom_qc: The file.info.qc.dicom-qc dictionary

    Returns:
        Tuple of (status, problem_checks) where:
          - status is "PASS" or "FAIL"
          - problem_checks is list of check names that failed or had invalid state
    """
    problem_checks: list[str] = []
    has_check_results = False

    for key, value in dicom_qc.items():
        if key == "job_info":
            continue

        if not isinstance(value, dict) or "state" not in value:
            continue

        has_check_results = True

        if value["state"] != "PASS":
            problem_checks.append(key)

    if not has_check_results or problem_checks:
        return ("FAIL", problem_checks)

    return ("PASS", [])


def run(*, file: FileEntry, proxy: FlywheelProxy) -> None:
    """Execute the dicom-qc-checker logic.

    Extracts DICOM QC metadata from the file, determines aggregate
    pass/fail status, logs failures, and tags the file accordingly.

    Args:
        file: The Flywheel file entry with metadata
        proxy: FlywheelProxy for persisting tag updates

    Raises:
        GearExecutionError: If tag persistence fails
    """
    dicom_qc: dict[str, Any] = file.info.get("qc", {}).get("dicom-qc", {})

    if not dicom_qc:
        log.warning("No DICOM QC results available for file %s", file.name)
        return

    # Check if there are any actual check results (non-job_info dicts with "state")
    has_check_results = any(
        isinstance(value, dict) and "state" in value
        for key, value in dicom_qc.items()
        if key != "job_info"
    )
    if not has_check_results:
        log.warning("No DICOM QC check results available for file %s", file.name)
        return

    status, problem_checks = determine_qc_status(dicom_qc)

    for check_name in problem_checks:
        log.warning("Check '%s' failed or has invalid state", check_name)

    gear_tags = GearTags(gear_name="dicom-qc-checker")
    updated_tags = gear_tags.update_tags(tags=file.tags, status=status)

    try:
        file.update(tags=updated_tags)
    except ApiException as exc:
        raise GearExecutionError(
            f"Failed to update tags for file {file.name}: {exc}"
        ) from exc
