"""Reusable mock factories for Pipeline Event Logger tests."""

from datetime import datetime
from typing import Any, Optional
from unittest.mock import Mock

from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import QCStatus


def create_mock_file_entry(
    *,
    name: str = "test-file.csv",
    info: Optional[dict[str, Any]] = None,
    modified: Optional[datetime] = None,
    parents: Optional[Mock] = None,
) -> Mock:
    """Factory for creating mock FileEntry objects.

    Args:
        name: Filename
        info: Custom info dict (qc metadata, data_identification, etc.)
        modified: File modification timestamp
        parents: Mock parents object with project attribute

    Returns:
        Mock FileEntry with configurable attributes
    """
    file_entry = Mock(spec=FileEntry)
    file_entry.name = name
    file_entry.info = info if info is not None else {}
    file_entry.modified = modified or datetime(2024, 6, 15, 10, 30, 0)
    file_entry.reload.return_value = file_entry

    if parents is None:
        parents = Mock()
        parents.project = "project_id_123"
    file_entry.parents = parents

    return file_entry


def create_mock_project_adaptor(
    *,
    label: str = "adrc-form-uds",
    group: str = "test-center",
    project_id: str = "project_id_123",
) -> Mock:
    """Factory for creating mock ProjectAdaptor objects.

    Args:
        label: Project label
        group: Project group (center)
        project_id: Project ID

    Returns:
        Mock ProjectAdaptor
    """
    project = Mock(spec=ProjectAdaptor)
    project.label = label
    project.group = group
    project.id = project_id
    project.get_pipeline_adcid = Mock(return_value=42)
    return project


def build_qc_info(
    gear_name: str,
    status: QCStatus = "PASS",
    errors: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a file.info dict with QC metadata for a given gear.

    Args:
        gear_name: Name of the upstream gear
        status: QC status value
        errors: List of error dicts (defaults to empty)

    Returns:
        Dict suitable for file_entry.info containing qc metadata
    """
    return {
        "qc": {
            gear_name: {
                "validation": {
                    "state": status,
                    "data": errors or [],
                    "cleared": [],
                },
            },
        },
    }


def build_data_identification_dict(
    *,
    ptid: str = "110001",
    adcid: int = 42,
    date: str = "2024-06-15",
    module: Optional[str] = "UDS",
    modality: Optional[str] = None,
    visitnum: Optional[str] = "1",
) -> dict[str, Any]:
    """Build a data_identification dict for file.info.

    Args:
        ptid: Participant ID
        adcid: Center ID
        date: Visit date
        module: Form module (mutually exclusive with modality)
        modality: Imaging modality (mutually exclusive with module)
        visitnum: Visit number

    Returns:
        Dict suitable for file_entry.info["data_identification"]
    """
    result: dict[str, Any] = {
        "ptid": ptid,
        "adcid": adcid,
        "date": date,
    }
    if module is not None:
        result["module"] = module
    if modality is not None:
        result["modality"] = modality
    if visitnum is not None:
        result["visitnum"] = visitnum
    return result
