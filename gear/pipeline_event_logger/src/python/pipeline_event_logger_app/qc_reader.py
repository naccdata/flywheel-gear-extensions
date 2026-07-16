"""General-purpose QC metadata reader for arbitrary upstream gears.

Reads the Flywheel QC convention: file.info.qc.<gear_name> contains
a job_info key (metadata about the gear run) and one or more check
result keys, each with at least a 'state' field.

This module does NOT use the form-specific models in error_models.py.
It handles the general case where we don't know the structure of the
check results ahead of time.
"""

import logging
from typing import Annotated, Any, Literal, Optional, Union

from flywheel.models.file_entry import FileEntry
from gear_execution.gear_execution import GearExecutionError
from nacc_common.error_models import FileError, FileErrorList, QCStatus
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# States recognized as valid QC outcomes
_VALID_STATES: set[str] = {"PASS", "FAIL", "IN REVIEW"}


class ListFieldMapping(BaseModel):
    """Field mapping for checks that produce a list of error dicts.

    Each field value is resolved against the source error dict:
    - If it matches a key in the source, the value from that key is used.
    - Otherwise, it is treated as a literal value.

    Example for dicom-validator:
        ListFieldMapping(type="list", message="name", error_code="dicom-validation")
        # "name" is a key in source -> uses source["name"]
        # "dicom-validation" is not a key -> used as literal
    """

    type: Literal["list"]
    message: str
    error_type: str = "error"
    error_code: str = "qc-error"
    value: Optional[str] = None


class StringFieldMapping(BaseModel):
    """Field mapping for checks that produce a string explanation on failure.

    The string value of the data field becomes the error message
    directly.
    """

    type: Literal["string"]
    error_type: str = "error"
    error_code: str = "qc-error"


class NoneFieldMapping(BaseModel):
    """Field mapping for checks that produce null data on failure.

    Synthesizes a "{check_name} failed" message when state is not PASS.
    """

    type: Literal["none"]
    error_type: str = "error"
    error_code: str = "qc-error"


FieldMapping = Annotated[
    Union[ListFieldMapping, StringFieldMapping, NoneFieldMapping],
    Field(discriminator="type"),
]


class QCErrorConfig(BaseModel):
    """Describes how to extract errors from a gear's QC check results.

    Attributes:
        check_name: Which check result to read errors from
            (e.g., "dicom-validator", "validation").
        data_key: Key within the check result holding the error data.
            Defaults to "data".
        field_mapping: Discriminated union describing the expected data
            shape and how to produce FileError objects from it.
    """

    check_name: str
    data_key: str = "data"
    field_mapping: FieldMapping


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

    def extract_errors(self, config: QCErrorConfig) -> FileErrorList:
        """Extract errors from this check result using the given config.

        Dispatches based on the field_mapping type:
        - "list": expects data to be a list of dicts, maps each item
        - "string": expects data to be a string, uses it as the message
        - "none": expects data to be null, synthesizes "{check_name} failed"

        Returns:
            FileErrorList of extracted errors. Empty if the check_name
            doesn't match, or if the check passed with no data.
        """
        if self._name != config.check_name:
            return FileErrorList([])

        raw_data = self._raw.get(config.data_key)
        mapping = config.field_mapping

        if isinstance(mapping, ListFieldMapping):
            return self._extract_from_list(raw_data, mapping)
        if isinstance(mapping, StringFieldMapping):
            return self._extract_from_string(raw_data, mapping)
        if isinstance(mapping, NoneFieldMapping):
            return self._extract_from_none(mapping)

        return FileErrorList([])

    def _extract_from_list(
        self, raw_data: Any, mapping: ListFieldMapping
    ) -> FileErrorList:
        """Extract errors from list-of-dicts data."""
        if not isinstance(raw_data, list):
            return FileErrorList([])

        errors: list[FileError] = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue

            message = _resolve_field(item, mapping.message, default="Unknown error")
            error_type = _resolve_field(item, mapping.error_type, default="error")
            error_code = _resolve_field(item, mapping.error_code, default="qc-error")
            value = (
                _resolve_field(item, mapping.value, default=None)
                if mapping.value
                else None
            )

            errors.append(
                FileError(
                    message=message,
                    error_type=error_type,
                    error_code=error_code,
                    value=value,
                )
            )
        return FileErrorList(errors)

    def _extract_from_string(
        self, raw_data: Any, mapping: StringFieldMapping
    ) -> FileErrorList:
        """Extract a single error from string data."""
        if not isinstance(raw_data, str):
            return FileErrorList([])

        return FileErrorList(
            [
                FileError(
                    message=raw_data,
                    error_type=mapping.error_type,
                    error_code=mapping.error_code,
                )
            ]
        )

    def _extract_from_none(self, mapping: NoneFieldMapping) -> FileErrorList:
        """Synthesize an error when data is null and state is not PASS."""
        if self.state and self.state != "PASS":
            return FileErrorList(
                [
                    FileError(
                        message=f"{self._name} failed",
                        error_type=mapping.error_type,
                        error_code=mapping.error_code,
                    )
                ]
            )
        return FileErrorList([])

    def __repr__(self) -> str:
        return f"GearQCResult(name={self._name!r}, state={self.state!r})"


def _resolve_field(item: dict[str, Any], field: str, default: Any) -> Any:
    """Resolve a field mapping value against a source dict.

    If `field` is a key in `item`, returns item[field]. Otherwise,
    returns `field` as a literal value. If the resolved value is None,
    returns `default`.
    """
    if field in item:
        resolved = item[field]
        return str(resolved) if resolved is not None else default
    return field if field is not None else default


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

    def extract_errors(
        self, error_configs: Optional[list[QCErrorConfig]] = None
    ) -> FileErrorList:
        """Extract errors from check results using the provided configs.

        Each config targets a specific check result by name and describes
        how to map its data into FileError objects.

        Args:
            error_configs: List of error extraction configs. If None or
                empty, returns an empty error list.

        Returns:
            Aggregated FileErrorList from all matching configs.
        """
        if not error_configs:
            return FileErrorList([])

        all_errors: list[FileError] = []
        for config in error_configs:
            result = self.get_result(config.check_name)
            if result is not None:
                extracted = result.extract_errors(config)
                all_errors.extend(extracted)

        return FileErrorList(all_errors)


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
