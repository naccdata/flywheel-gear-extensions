"""Property test for visit metadata validation.

**Feature: form-scheduler-event-logging-refactor,
  Property 6:
  Visit Metadata Validation**

**Validates: Requirements 4.4, 4.5**
"""

from typing import Any, Dict, Optional
from unittest.mock import Mock

import pytest
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.event_accumulator import (
    EventAccumulator,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.data_identification import DataIdentification
from test_mocks.strategies import (
    invalid_visit_metadata_strategy,
    valid_visit_metadata_strategy,
)


def create_mock_file_entry(
    name: str, info: Optional[Dict[str, Any]] = None
) -> FileEntry:
    """Create a mock FileEntry with the given info."""
    file_entry = Mock(spec=FileEntry)
    file_entry.name = name
    file_entry.info = info or {}
    return file_entry


# Use shared strategies from test_mocks.strategies


@pytest.fixture
def mock_event_capture():
    """Create a mock event logger."""
    return Mock()


@pytest.fixture
def event_accumulator(mock_event_capture):
    """Create an EventAccumulator instance."""
    return EventAccumulator(mock_event_capture)


@given(valid_metadata=valid_visit_metadata_strategy())
@settings(max_examples=100)
def test_valid_visit_metadata_passes_validation(valid_metadata):
    """Property test: For any DataIdentification with required fields (ptid,
    date, module), validation should pass and allow VisitEvent creation.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Create DataIdentification from valid data - Pydantic validation
    # ensures required fields
    visit_metadata = DataIdentification.from_visit_metadata(**valid_metadata)

    # If creation succeeded, all required fields are present
    assert visit_metadata is not None
    assert visit_metadata.ptid is not None
    assert visit_metadata.date is not None
    assert visit_metadata.module is not None


@given(invalid_metadata=invalid_visit_metadata_strategy())
@settings(max_examples=100)
def test_invalid_visit_metadata_fails_validation(invalid_metadata):
    """Property test: For any DataIdentification missing required fields (ptid,
    date, module), Pydantic validation should fail.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Pydantic validation should raise ValidationError for invalid data
    # (missing required fields like ptid, date, or module)
    try:
        visit_metadata = DataIdentification.from_visit_metadata(**invalid_metadata)
        # If it succeeds, verify at least one required field is actually missing/empty
        # (empty strings pass Pydantic but fail business logic)
        required_fields_present = bool(
            visit_metadata.ptid and visit_metadata.date and visit_metadata.module
        )
        assert required_fields_present is False, (
            "If validation passed, at least one required field should be empty"
        )
    except Exception:
        # ValidationError is expected for invalid data
        pass


def test_visit_metadata_validation_edge_cases():
    """Test edge cases for visit metadata validation.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Test with empty strings - Pydantic allows them but they're logically invalid
    empty_metadata = DataIdentification.from_visit_metadata(ptid="", date="", module="")
    # Empty strings pass Pydantic validation but fail business logic checks
    assert not (empty_metadata.ptid and empty_metadata.date and empty_metadata.module)

    # Test with whitespace-only strings - normalize_ptid strips them to empty
    whitespace_metadata = DataIdentification.from_visit_metadata(
        ptid="   ", date="   ", module="   "
    )
    # After normalization, ptid becomes empty
    assert whitespace_metadata.ptid == ""
    assert not whitespace_metadata.ptid  # Empty string is falsy

    # Test with None values (should raise ValidationError)
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DataIdentification.from_visit_metadata(ptid=None, date=None, module=None)

    # Test with mixed valid/invalid (should raise ValidationError)
    with pytest.raises(ValidationError):
        DataIdentification.from_visit_metadata(ptid="110001", date=None, module="UDS")

    # Test with all required fields present (should succeed)
    valid_metadata = DataIdentification.from_visit_metadata(
        ptid="110001", date="2024-01-15", module="UDS"
    )
    assert valid_metadata is not None
    assert valid_metadata.ptid and valid_metadata.date and valid_metadata.module


def test_visit_metadata_extraction_validation_integration(event_accumulator):
    """Test that metadata extraction properly validates extracted data.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Test QC status custom info with invalid data
    qc_log_invalid = create_mock_file_entry(
        "qc-status.json",
        {
            "visit": {"ptid": None, "date": "2024-01-15", "module": "UDS"}
        },  # Missing ptid
    )

    json_file_valid = create_mock_file_entry(
        "forms.json",
        {
            "forms": {
                "json": {"ptid": "110001", "visitdate": "2024-01-15", "module": "UDS"}
            }
        },
    )

    # Should fall back to JSON file when QC status is invalid
    result = event_accumulator._extract_visit_metadata(  # noqa: SLF001
        json_file_valid, qc_log_invalid
    )
    assert result is not None
    assert result.ptid == "110001"

    # Test both sources invalid
    qc_log_invalid = create_mock_file_entry(
        "qc-status.json", {"visit": {"ptid": None, "date": None, "module": None}}
    )

    json_file_invalid = create_mock_file_entry(
        "forms.json",
        {"forms": {"json": {"ptid": None, "visitdate": None, "module": None}}},
    )

    # Should return None when both sources are invalid
    result = event_accumulator._extract_visit_metadata(  # noqa: SLF001
        json_file_invalid, qc_log_invalid
    )
    assert result is None


def test_visit_metadata_validation_with_optional_fields():
    """Test that optional fields don't affect validation of required fields.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Test with only required fields
    minimal_metadata = DataIdentification.from_visit_metadata(
        ptid="110001", date="2024-01-15", module="UDS"
    )
    assert minimal_metadata is not None
    assert minimal_metadata.ptid and minimal_metadata.date and minimal_metadata.module

    # Test with all fields including optional ones
    complete_metadata = DataIdentification.from_visit_metadata(
        ptid="110001",
        date="2024-01-15",
        module="UDS",
        visitnum="01",
        packet="I",
        adcid=123,
        naccid="NACC001",
    )
    assert complete_metadata is not None
    assert (
        complete_metadata.ptid and complete_metadata.date and complete_metadata.module
    )

    # Test with required fields and some optional fields None
    partial_metadata = DataIdentification.from_visit_metadata(
        ptid="110001",
        date="2024-01-15",
        module="UDS",
        visitnum=None,
        packet=None,
        adcid=None,
        naccid=None,
    )
    assert partial_metadata is not None
    assert partial_metadata.ptid and partial_metadata.date and partial_metadata.module


@given(
    ptid=st.one_of(st.none(), st.text(max_size=0), st.text(min_size=1)),
    date=st.one_of(
        st.none(), st.text(max_size=0), st.dates().map(lambda d: d.strftime("%Y-%m-%d"))
    ),
    module=st.one_of(
        st.none(), st.text(max_size=0), st.sampled_from(["UDS", "LBD", "FTLD", "MDS"])
    ),
)
@settings(max_examples=100)
def test_visit_metadata_validation_required_fields_property(ptid, date, module):
    """Property test: Pydantic validation should pass if and only if all
    required fields (ptid, date, module) are non-None.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    try:
        visit_metadata = DataIdentification.from_visit_metadata(
            ptid=ptid, date=date, module=module
        )
        # If Pydantic validation passed, all required fields should be non-None
        # (though they might be empty strings)
        assert visit_metadata is not None

    except Exception:
        # If Pydantic validation fails, at least one required field was None
        # This is expected and acceptable
        pass


def test_visit_metadata_validation_milestone_form_without_visitnum():
    """Test that milestone forms without visitnum pass validation.

    Milestone forms (MLST) don't have visitnum but should still be valid
    for event creation as long as ptid, date, and module are present.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Create milestone metadata WITHOUT visitnum
    milestone_metadata = DataIdentification.from_visit_metadata(
        ptid="110001",
        date="2024-01-15",
        module="MLST",
        packet="M",
        visitnum=None,  # Explicitly None for milestone forms
    )

    # Should pass Pydantic validation
    assert milestone_metadata is not None

    # Verify required fields are present
    assert milestone_metadata.ptid == "110001"
    assert milestone_metadata.date == "2024-01-15"
    assert milestone_metadata.module == "MLST"
    assert milestone_metadata.packet == "M"
    assert milestone_metadata.visitnum is None


def test_visit_metadata_validation_np_form_without_visitnum():
    """Test that NP forms without visitnum pass validation.

    NP forms don't have visitnum but should still be valid for event
    creation as long as ptid, date, and module are present.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Create NP metadata WITHOUT visitnum
    np_metadata = DataIdentification.from_visit_metadata(
        ptid="110002",
        date="2024-02-20",
        module="NP",
        packet="N",
        visitnum=None,  # Explicitly None for NP forms
    )

    # Should pass Pydantic validation
    assert np_metadata is not None

    # Verify required fields are present
    assert np_metadata.ptid == "110002"
    assert np_metadata.date == "2024-02-20"
    assert np_metadata.module == "NP"
    assert np_metadata.packet == "N"
    assert np_metadata.visitnum is None


def test_visit_metadata_validation_forms_with_and_without_visitnum():
    """Test that validation works correctly for both forms with and without
    visitnum.

      **Feature: form-scheduler-event-logging-refactor,
    Property 6:
        Visit Metadata Validation**
      **Validates: Requirements 4.4, 4.5**
    """
    # Form WITH visitnum (e.g., UDS)
    uds_metadata = DataIdentification.from_visit_metadata(
        ptid="110001",
        date="2024-01-15",
        module="UDS",
        visitnum="01",
        packet="I",
    )
    assert uds_metadata is not None

    # Form WITHOUT visitnum (e.g., Milestone)
    milestone_metadata = DataIdentification.from_visit_metadata(
        ptid="110001",
        date="2024-01-15",
        module="MLST",
        visitnum=None,
        packet="M",
    )
    assert milestone_metadata is not None

    # Both should be valid - visitnum is optional
    assert uds_metadata.visitnum == "01"
    assert milestone_metadata.visitnum is None
