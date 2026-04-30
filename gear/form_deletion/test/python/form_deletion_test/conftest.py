"""Shared fixtures for form_deletion tests."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from configs.ingest_configs import (
    FormProjectConfigs,
    LabelTemplate,
    ModuleConfigs,
    SupplementModuleConfigs,
    UploadTemplateInfo,
)
from deletions.models import DeletedItems, DeleteRequest
from identifiers.model import IdentifierObject
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_flywheel import MockFile, MockProjectAdaptor


class MockProjectAdaptorForDeletion(MockProjectAdaptor):
    """Extended MockProjectAdaptor with delete_file and find_subject
    support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subject_map: dict = {}
        self._delete_results: dict = {}
        self._fw = MagicMock()  # type: ignore

    def delete_file(self, filename: str) -> bool:
        """Returns a configured result; defaults to True if file exists."""
        if filename in self._delete_results:
            return self._delete_results[filename]
        return self.get_file(filename) is not None

    def find_subject(self, label: str):
        return self._subject_map.get(label)

    def set_subject(self, label: str, subject) -> None:
        self._subject_map[label] = subject

    def set_delete_result(self, filename: str, result: bool) -> None:
        self._delete_results[filename] = result


@pytest.fixture
def delete_request():
    return DeleteRequest(
        ptid="adrc1010", module="uds", visitdate="2024-01-15", visitnum="1"
    )


@pytest.fixture
def active_identifier():
    return IdentifierObject(
        ptid="adrc1010",
        adcid=42,
        naccadc=42,
        naccid="NACC123456",
        guid=None,
        active=True,
    )


@pytest.fixture
def inactive_identifier():
    return IdentifierObject(
        ptid="adrc1010",
        adcid=42,
        naccadc=42,
        naccid="NACC123456",
        guid=None,
        active=False,
    )


@pytest.fixture
def uds_module_configs():
    return ModuleConfigs(
        initial_packets=["I"],
        followup_packets=["F"],
        versions=["3"],
        date_field="visitdate",
        hierarchy_labels=UploadTemplateInfo(
            session=LabelTemplate(template="$module-$visitdate-$visitnum"),
            acquisition=LabelTemplate(template="$module"),
            filename=LabelTemplate(template="$subject-$session-$acquisition.json"),
        ),
        required_fields=["ptid", "visitdate"],
        longitudinal=True,
    )


@pytest.fixture
def tfp_module_configs():
    """A TFP module that supplements (depends on) UDS."""
    return ModuleConfigs(
        initial_packets=["I"],
        followup_packets=["F"],
        versions=["3"],
        date_field="tfpdate",
        hierarchy_labels=UploadTemplateInfo(
            session=LabelTemplate(template="$module-$tfpdate-$visitnum"),
            acquisition=LabelTemplate(template="$module"),
            filename=LabelTemplate(template="$subject-$session-$acquisition.json"),
        ),
        required_fields=[],
        supplement_module=SupplementModuleConfigs(
            label="UDS", date_field="tfpdate", exact_match=True
        ),
    )


@pytest.fixture
def form_configs(uds_module_configs):
    return FormProjectConfigs(
        primary_key="ptid",
        accepted_modules=["UDS"],
        module_configs={"UDS": uds_module_configs},
    )


@pytest.fixture
def form_configs_with_dep(uds_module_configs, tfp_module_configs):
    """FormProjectConfigs where TFP depends on UDS."""
    return FormProjectConfigs(
        primary_key="ptid",
        accepted_modules=["UDS", "TFP"],
        module_configs={"UDS": uds_module_configs, "TFP": tfp_module_configs},
    )


@pytest.fixture
def request_time():
    return datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def error_log_name():
    return "NACC123456-UDS-2024-01-15-1.json"


@pytest.fixture
def old_error_log_file(error_log_name):
    """Error log file modified BEFORE the request time — valid for deletion."""
    return MockFile(
        name=error_log_name,
        modified=datetime(2024, 1, 14, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def new_error_log_file(error_log_name):
    """Error log file modified AFTER the request time — should be rejected."""
    return MockFile(
        name=error_log_name,
        modified=datetime(2024, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_project(old_error_log_file):
    project = MockProjectAdaptorForDeletion(label="ingest-form-nacc")
    project.add_file(old_error_log_file)
    return project


@pytest.fixture
def error_writer():
    return ListErrorWriter(container_id="file-123", fw_path="group/project/file.json")


@pytest.fixture
def deleted_items():
    return DeletedItems()
