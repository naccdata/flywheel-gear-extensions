"""Property test for QC status log to JSON file matching.

**Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**

**Validates: Requirements 2.5**
"""

from typing import Any, Dict, Optional
from unittest.mock import Mock

import pytest
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from form_scheduler_app.simplified_event_accumulator import EventAccumulator
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


def create_mock_file_entry(
    name: str, info: Optional[Dict[str, Any]] = None
) -> FileEntry:
    """Create a mock FileEntry with the given info."""
    file_entry = Mock(spec=FileEntry)
    file_entry.name = name
    file_entry.info = info or {}
    return file_entry


@st.composite
def json_file_forms_metadata_strategy(draw):
    """Generate JSON file forms metadata for testing."""
    # Generate ptid that won't become empty after lstrip("0")
    ptid_base = draw(
        st.text(
            min_size=1, max_size=8, alphabet=st.characters(whitelist_categories=("Lu",))
        )
    )
    ptid_prefix = draw(st.text(min_size=0, max_size=3, alphabet="0"))
    ptid = ptid_prefix + ptid_base  # Ensures ptid won't be all zeros

    return {
        "ptid": ptid,
        "visitnum": draw(
            st.text(
                min_size=1,
                max_size=3,
                alphabet=st.characters(whitelist_categories=("Nd",)),
            )
        ),
        "visitdate": draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d"))),
        "module": draw(st.sampled_from(["UDS", "LBD", "FTLD", "MDS"])),
        "packet": draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))),
        "adcid": draw(st.integers(min_value=1, max_value=999)),
    }


@pytest.fixture
def mock_event_logger():
    """Create a mock event logger."""
    return Mock()


@pytest.fixture
def mock_project():
    """Create a mock project that can find files."""
    project = Mock(spec=ProjectAdaptor)
    project.label = "test-project"
    project.group = "test-center"
    project.get_pipeline_adcid.return_value = 123

    # Mock file storage for get_file method
    project._files = {}

    def mock_get_file(filename):
        if filename in project._files:
            return project._files[filename]
        else:
            raise FileNotFoundError(f"File {filename} not found")

    project.get_file = mock_get_file
    return project


@pytest.fixture
def event_accumulator(mock_event_logger):
    """Create an EventAccumulator instance."""
    return EventAccumulator(mock_event_logger)


@given(forms_metadata=json_file_forms_metadata_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_qc_status_log_matching_success(
    event_accumulator, mock_project, forms_metadata
):
    """Property test: For any JSON file with valid forms metadata, the system
    should correctly find its corresponding QC status log using
    ErrorLogTemplate.

    **Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**
    **Validates: Requirements 2.5**
    """
    # Create JSON file with forms metadata
    json_file = create_mock_file_entry(
        "forms.json", {"forms": {"json": forms_metadata}}
    )

    # Generate expected QC status log filename using ErrorLogTemplate format
    # Format: {ptid}_{date}_{module}_qc-status.log
    module = forms_metadata["module"]
    ptid = forms_metadata["ptid"].strip().lstrip("0")
    # ErrorLogTemplate returns None if ptid becomes empty after cleaning
    if not ptid:
        # This is a valid case where ErrorLogTemplate would return None
        result = event_accumulator.find_qc_status_for_json_file(json_file, mock_project)
        assert result is None
        return

    visitdate = forms_metadata["visitdate"]
    expected_qc_log_name = f"{ptid}_{visitdate}_{module.lower()}_qc-status.log"

    # Create corresponding QC status log file and add to project
    qc_log_file = create_mock_file_entry(expected_qc_log_name)
    mock_project._files[expected_qc_log_name] = qc_log_file

    # Test that the matching works
    result = event_accumulator.find_qc_status_for_json_file(json_file, mock_project)

    assert result is not None
    assert result.name == expected_qc_log_name


@given(forms_metadata=json_file_forms_metadata_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_qc_status_log_matching_not_found(
    event_accumulator, mock_project, forms_metadata
):
    """Property test: For any JSON file where the corresponding QC status log
    doesn't exist, the system should return None.

    **Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**
    **Validates: Requirements 2.5**
    """
    # Create JSON file with forms metadata
    json_file = create_mock_file_entry(
        "forms.json", {"forms": {"json": forms_metadata}}
    )

    # Don't add any QC status log files to the project
    # (mock_project._files remains empty)

    # Test that matching returns None when file not found
    result = event_accumulator.find_qc_status_for_json_file(json_file, mock_project)

    assert result is None


def test_qc_status_log_matching_invalid_json_file(event_accumulator, mock_project):
    """Test that JSON files without forms metadata return None.

    **Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**
    **Validates: Requirements 2.5**
    """
    # Test with no forms metadata
    json_file_no_forms = create_mock_file_entry("forms.json", {})
    result = event_accumulator.find_qc_status_for_json_file(
        json_file_no_forms, mock_project
    )
    assert result is None

    # Test with empty forms.json
    json_file_empty_forms = create_mock_file_entry(
        "forms.json", {"forms": {"json": {}}}
    )
    result = event_accumulator.find_qc_status_for_json_file(
        json_file_empty_forms, mock_project
    )
    assert result is None

    # Test with missing module
    json_file_no_module = create_mock_file_entry(
        "forms.json", {"forms": {"json": {"ptid": "110001", "visitnum": "01"}}}
    )
    result = event_accumulator.find_qc_status_for_json_file(
        json_file_no_module, mock_project
    )
    assert result is None


def test_qc_status_log_matching_error_handling(event_accumulator, mock_project):
    """Test that file access errors are handled gracefully.

    **Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**
    **Validates: Requirements 2.5**
    """
    # Create JSON file with valid metadata
    forms_metadata = {"ptid": "110001", "visitnum": "01", "module": "UDS", "adcid": 123}

    json_file = create_mock_file_entry(
        "forms.json", {"forms": {"json": forms_metadata}}
    )

    # Mock project.get_file to raise an exception
    def mock_get_file_error(filename):
        raise Exception("File access error")

    mock_project.get_file = mock_get_file_error

    # Should handle error gracefully and return None
    result = event_accumulator.find_qc_status_for_json_file(json_file, mock_project)
    assert result is None


def test_error_log_template_integration(event_accumulator, mock_project):
    """Test integration with ErrorLogTemplate for filename generation.

    **Feature: form-scheduler-event-logging-refactor, Property 5: QC Status Log to JSON File Matching**
    **Validates: Requirements 2.5**
    """
    # Test with realistic forms metadata
    forms_metadata = {
        "ptid": "110001",
        "visitnum": "01",
        "visitdate": "2024-01-15",
        "module": "UDS",
        "packet": "I",
        "adcid": 123,
    }

    json_file = create_mock_file_entry(
        "forms.json", {"forms": {"json": forms_metadata}}
    )

    # Generate expected filename using ErrorLogTemplate format
    # Format: {ptid}_{date}_{module}_qc-status.log
    expected_filename = "110001_2024-01-15_uds_qc-status.log"

    # Add the expected file to the project
    qc_log_file = create_mock_file_entry(expected_filename)
    mock_project._files[expected_filename] = qc_log_file

    # Test the matching
    result = event_accumulator.find_qc_status_for_json_file(json_file, mock_project)

    # Verify the correct file was found
    assert result is not None
    assert result.name == expected_filename
