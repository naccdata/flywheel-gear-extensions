"""General-purpose QC metadata reader for arbitrary upstream gears.

Reads the Flywheel QC convention: file.info.qc.<gear_name> contains
a job_info key (metadata about the gear run) and one or more check
result keys, each with at least a 'state' field.

This module does NOT use the form-specific models in error_models.py.
It handles the general case where we don't know the structure of the
check results ahead of time.
"""

import logging
from typing import Any

from flywheel.models.file_entry import FileEntry
from gear_execution.gear_execution import GearExecutionError
from nacc_common.error_models import QCStatus

log = logging.getLogger(__name__)

# States recognized as valid QC outcomes
_VALID_STATES: set[str] = {"PASS", "FAIL", "IN REVIEW"}


class GearQCResult:
    """A single QC check result from a gear.

    Wraps the raw dict written by add_qc_result. The only guaranteed
    field is 'state'. All other fields are gear-specific.

    Example:
        result.state         # "PASS" or "FAIL" or "IN REVIEW"
        result.get("data")   # check-specific findings, or None
        result.keys()        # all available field names
    """

    def __init__(self, name: str, raw: dict[str, Any]):
        self._name = name
        self._raw = raw

    @property
    def name(self) -> str:
        """The check name (e.g., 'validation', 'dicom-validator')."""
        return self._name

    @property
    def state(self) -> str | None:
        """The QC state for this check result."""
        state = self._raw.get("state")
        if isinstance(state, str) and state in _VALID_STATES:
            return state
        return None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a field value by key."""
        return self._raw.get(key, default)

    def keys(self) -> list[str]:
        """All field names in this check result."""
        return list(self._raw.keys())

    def __repr__(self) -> str:
        return f"GearQCResult(name={self._name!r}, state={self.state!r})"


class GearQC:
    """QC metadata for a single gear on a file.

    Wraps the raw dict at file.info.qc.<gear_name>, providing access
    to individual check results and aggregate status.

    Example:
        gear_qc = GearQC.from_file(file_entry, "dicom-qc")
        gear_qc.status              # "FAIL" (aggregate)
        gear_qc.results             # list of GearQCResult
        gear_qc.get_result("bed_moving")  # specific check
    """

    def __init__(self, gear_name: str, raw: dict[str, Any]):
        self._gear_name = gear_name
        self._results = [
            GearQCResult(name=key, raw=value)
            for key, value in raw.items()
            if key != "job_info" and isinstance(value, dict)
        ]

    @classmethod
    def from_file(cls, file_entry: FileEntry, gear_name: str) -> "GearQC":
        """Create a GearQC from a file entry.

        Args:
            file_entry: The file entry to read QC info from
            gear_name: The upstream gear name to look up

        Returns:
            GearQC instance

        Raises:
            GearExecutionError: If QC metadata is missing
        """
        raw = _get_gear_qc_dict(file_entry, gear_name)
        return cls(gear_name, raw)

    @property
    def gear_name(self) -> str:
        return self._gear_name

    @property
    def results(self) -> list[GearQCResult]:
        """All check results (excluding job_info)."""
        return self._results

    def get_result(self, name: str) -> GearQCResult | None:
        """Get a specific check result by name."""
        for result in self._results:
            if result.name == name:
                return result
        return None

    @property
    def status(self) -> QCStatus | None:
        """Aggregate QC status across all check results.

        Priority: FAIL > IN REVIEW > PASS.
        Returns None if no valid states found.
        """
        states = {r.state for r in self._results if r.state is not None}
        if not states:
            return None
        if "FAIL" in states:
            return "FAIL"
        if "IN REVIEW" in states:
            return "IN REVIEW"
        return "PASS"


def read_gear_qc_status(
    file_entry: FileEntry,
    gear_name: str,
) -> QCStatus:
    """Read the aggregate QC status for a gear from file.info.qc.

    Convenience function that creates a GearQC and returns its status.

    Args:
        file_entry: The file entry to read QC info from
        gear_name: The upstream gear name to look up

    Returns:
        The aggregate QCStatus

    Raises:
        GearExecutionError: If QC metadata is missing or has no valid states
    """
    gear_qc = GearQC.from_file(file_entry, gear_name)

    status = gear_qc.status
    if status is None:
        raise GearExecutionError(
            f"No QC check results with valid state found for gear "
            f"'{gear_name}' on file {file_entry.name}"
        )

    return status


def _get_gear_qc_dict(file_entry: FileEntry, gear_name: str) -> dict[str, Any]:
    """Extract the raw qc dict for a gear from file.info.

    Args:
        file_entry: The file entry
        gear_name: The gear name to look up

    Returns:
        The raw dict at file.info.qc.<gear_name>

    Raises:
        GearExecutionError: If qc or gear entry is missing
    """
    file_entry = file_entry.reload()
    filename = file_entry.name

    if not file_entry.info:
        raise GearExecutionError(f"file.info is empty on {filename}")

    qc = file_entry.info.get("qc")
    if not qc or not isinstance(qc, dict):
        raise GearExecutionError(f"file.info.qc not found on {filename}")

    gear_qc = qc.get(gear_name)
    if not gear_qc or not isinstance(gear_qc, dict):
        raise GearExecutionError(
            f"QC results for gear '{gear_name}' not found in file.info.qc on {filename}"
        )

    return gear_qc
