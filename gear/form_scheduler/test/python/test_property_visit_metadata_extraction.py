"""Property test for visit metadata extraction priority.

**Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**

**Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
"""

from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import Mock

import pytest
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from form_scheduler_app.simplified_event_accumulator import (
    EventAccumulator,
    VisitMetadataExtractor,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nacc_common.error_models import VisitMetadata


def create_mock_file_entry(
    name: str, info: Optional[Dict[str, Any]] = None
) -> FileEntry:
    """Create a mock FileEntry with the given info."""
    file_entry = Mock(spec=FileEntry)
    file_entry.name = name
    file_entry.info = info or {}
    return file_entry


@st.composite
def visit_metadata_strategy(draw):
    """Generate valid VisitMetadata for testing."""
    return {
        "ptid": draw(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(whitelist_categories=("Nd", "Lu")),
            )
        ),
        "visitnum": draw(
            st.text(
                min_size=1,
                max_size=3,
                alphabet=st.characters(whitelist_categories=["Nd"]),
            )
        ),
        "date": draw(
            st.dates(
                min_value=datetime(2020, 1, 1).date(),
                max_value=datetime(2024, 12, 31).date(),
            )
        ).strftime("%Y-%m-%d"),
        "module": draw(st.sampled_from(["UDS", "LBD", "FTLD", "MDS"])),
        "packet": draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))),
        "adcid": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=999))),
        "naccid": draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
    }


@st.composite
def json_file_metadata_strategy(draw):
    """Generate JSON file metadata with visitdate field."""
    metadata = draw(visit_metadata_strategy())
    # JSON files use 'visitdate' instead of 'date'
    json_metadata = {**metadata}
    if "date" in json_metadata:
        json_metadata["visitdate"] = json_metadata.pop("date")
    return json_metadata


@pytest.fixture
def mock_event_logger():
    """Create a mock event logger."""
    return Mock()


@pytest.fixture
def mock_project():
    """Create a mock project."""
    project = Mock(spec=ProjectAdaptor)
    project.label = "test-project"
    project.group = "test-center"
    project.get_pipeline_adcid.return_value = 123
    return project


@pytest.fixture
def event_accumulator(mock_event_logger):
    """Create an EventAccumulator instance."""
    return EventAccumulator(mock_event_logger)


@given(visit_data=visit_metadata_strategy(), json_data=json_file_metadata_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_visit_metadata_extraction_priority_custom_info_first(
    event_accumulator, visit_data, json_data
):
    """Property test: When both QC status custom info and JSON metadata are
    available, custom info should be used first.

    **Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**
    **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
    """
    # Create QC status file with custom info containing visit metadata
    qc_log_file = create_mock_file_entry("qc-status.json", {"visit": visit_data})

    # Create JSON file with different metadata
    json_file = create_mock_file_entry("forms.json", {"forms": {"json": json_data}})

    # Extract metadata - should prioritize QC status custom info
    result = event_accumulator._extract_visit_metadata(json_file, qc_log_file)

    # Should successfully extract from custom info if valid
    if visit_data.get("ptid") and visit_data.get("date") and visit_data.get("module"):
        assert result is not None
        assert result.ptid == visit_data["ptid"]
        assert result.date == visit_data["date"]
        assert result.module == visit_data["module"]
        assert result.packet == visit_data.get("packet")
    else:
        # If custom info is invalid, should fall back to JSON metadata
        if (
            json_data.get("ptid")
            and json_data.get("visitdate")
            and json_data.get("module")
        ):
            assert result is not None
            assert result.ptid == json_data["ptid"]
            assert result.date == json_data["visitdate"]  # Maps visitdate -> date
            assert result.module == json_data["module"]


@given(json_data=json_file_metadata_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_visit_metadata_extraction_fallback_to_json(event_accumulator, json_data):
    """Property test: When QC status custom info is not available, should fall
    back to JSON file metadata.

    **Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**
    **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
    """
    # Create QC status file without custom info
    qc_log_file = create_mock_file_entry("qc-status.json", {})

    # Create JSON file with metadata
    json_file = create_mock_file_entry("forms.json", {"forms": {"json": json_data}})

    # Extract metadata - should use JSON file metadata
    result = event_accumulator._extract_visit_metadata(json_file, qc_log_file)

    # Should extract from JSON metadata if valid
    if json_data.get("ptid") and json_data.get("visitdate") and json_data.get("module"):
        assert result is not None
        assert result.ptid == json_data["ptid"]
        assert result.date == json_data["visitdate"]  # Maps visitdate -> date
        assert result.module == json_data["module"]
        assert result.packet == json_data.get("packet")
    else:
        assert result is None


@given(visit_data=visit_metadata_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_visit_metadata_extraction_no_qc_file(event_accumulator, visit_data):
    """Property test: When QC status file is None, should fall back to JSON
    file metadata.

    **Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**
    **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
    """
    # Convert visit_data to JSON format (visitdate instead of date)
    json_data = {**visit_data}
    if "date" in json_data:
        json_data["visitdate"] = json_data.pop("date")

    # Create JSON file with metadata
    json_file = create_mock_file_entry("forms.json", {"forms": {"json": json_data}})

    # Extract metadata with no QC file
    result = event_accumulator._extract_visit_metadata(json_file, None)

    # Should extract from JSON metadata if valid
    if json_data.get("ptid") and json_data.get("visitdate") and json_data.get("module"):
        assert result is not None
        assert result.ptid == json_data["ptid"]
        assert result.date == json_data["visitdate"]  # Maps visitdate -> date
        assert result.module == json_data["module"]
        assert result.packet == json_data.get("packet")
    else:
        assert result is None


def test_visit_metadata_extraction_invalid_data(event_accumulator):
    """Test that invalid metadata returns None.

    **Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**
    **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
    """
    # Create files with invalid metadata (missing required fields)
    qc_log_file = create_mock_file_entry(
        "qc-status.json",
        {"visit": {"ptid": None, "date": None, "module": None}},  # Invalid
    )

    json_file = create_mock_file_entry(
        "forms.json",
        {
            "forms": {"json": {"ptid": None, "visitdate": None, "module": None}}
        },  # Invalid
    )

    # Should return None for invalid data
    result = event_accumulator._extract_visit_metadata(json_file, qc_log_file)
    assert result is None


def test_visit_metadata_extractor_utilities():
    """Test the VisitMetadataExtractor utility methods.

    **Feature: form-scheduler-event-logging-refactor, Property 4: Visit Metadata Extraction Priority**
    **Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**
    """
    # Test from_qc_status_custom_info
    custom_info = {
        "visit": {
            "ptid": "110001",
            "date": "2024-01-15",
            "module": "UDS",
            "packet": "I",
        }
    }

    result = VisitMetadataExtractor.from_qc_status_custom_info(custom_info)
    assert result is not None
    assert result.ptid == "110001"
    assert result.date == "2024-01-15"
    assert result.module == "UDS"
    assert result.packet == "I"

    # Test from_json_file_metadata
    json_file = create_mock_file_entry(
        "forms.json",
        {
            "forms": {
                "json": {
                    "ptid": "110002",
                    "visitdate": "2024-01-16",
                    "module": "LBD",
                    "packet": "F",
                }
            }
        },
    )

    result = VisitMetadataExtractor.from_json_file_metadata(json_file)
    assert result is not None
    assert result.ptid == "110002"
    assert result.date == "2024-01-16"  # visitdate mapped to date
    assert result.module == "LBD"
    assert result.packet == "F"

    # Test is_valid_for_event
    valid_metadata = VisitMetadata(ptid="110001", date="2024-01-15", module="UDS")
    assert VisitMetadataExtractor.is_valid_for_event(valid_metadata) is True

    invalid_metadata = VisitMetadata(ptid=None, date="2024-01-15", module="UDS")
    assert VisitMetadataExtractor.is_valid_for_event(invalid_metadata) is False
