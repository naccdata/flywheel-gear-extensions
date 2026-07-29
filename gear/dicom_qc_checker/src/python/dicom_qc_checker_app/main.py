"""Core business logic for the dicom-qc-checker gear."""

import logging
from typing import Any, Optional

from flywheel.models.file_entry import FileEntry

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


def run(*, file: FileEntry) -> Optional[str]:
    """Execute the dicom-qc-checker logic.

    Extracts DICOM QC metadata from the file, determines aggregate
    pass/fail status, and logs failures.

    Args:
        file: The Flywheel file entry with metadata

    Returns:
        The status string ("PASS" or "FAIL"), or None if no QC metadata
        is available (early exit case).
    """
    info = file.info or {}
    dicom_qc: dict[str, Any] = info.get("qc", {}).get("dicom-qc", {})

    if not dicom_qc:
        log.warning("No DICOM QC results available for file %s", file.name)
        return None

    status, problem_checks = determine_qc_status(dicom_qc)

    # If status is FAIL only because there were no check results,
    # treat it as "nothing to do" rather than a real failure.
    if status == "FAIL" and not problem_checks:
        log.warning("No DICOM QC check results available for file %s", file.name)
        return None

    for check_name in problem_checks:
        log.warning("Check '%s' failed or has invalid state", check_name)

    return status
