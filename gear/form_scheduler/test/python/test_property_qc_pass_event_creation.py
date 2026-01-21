"""Property test for QC-pass event creation only.

**Feature: form-scheduler-event-logging-refactor,
  Property 1: QC-Pass Event Creation Only**
**Validates: Requirements 1.1, 1.2**
"""

from datetime import datetime
from unittest.mock import Mock

from assertions import assert_valid_qc_pass_event
from event_capture.visit_events import ACTION_PASS_QC
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.event_accumulator import EventAccumulator
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import QC_STATUS_PASS
from test_mocks.mock_event_capture import MockVisitEventCapture
from test_mocks.mock_factories import FileEntryFactory
from test_mocks.mock_flywheel import MockProjectAdaptor
from test_mocks.strategies import json_file_strategy as shared_json_strategy
from test_mocks.strategies import qc_status_strategy


@st.composite
def json_file_strategy(draw):
    """Generate random JSON file data using shared strategy."""
    forms_json = draw(shared_json_strategy())

    file_entry = Mock(spec=FileEntry)
    file_entry.name = (
        f"{forms_json['ptid']}"
        f"_{forms_json['visitdate']}"
        f"_{forms_json['module'].lower()}.json"
    )
    file_entry.info = {"forms": {"json": forms_json}}
    file_entry.created = datetime.now()

    return file_entry


@given(json_file=json_file_strategy(), qc_status=qc_status_strategy())
@settings(max_examples=100)
def test_qc_pass_event_creation_only(json_file: FileEntry, qc_status: str):
    """Property test: Only create QC-pass events for visits that pass QC
    validation.

      **Feature: form-scheduler-event-logging-refactor,
    Property 1: QC-Pass Event Creation Only**
      **Validates: Requirements 1.1, 1.2**

      For any pipeline completion, the system should create QC-pass events only
      for visits that pass QC validation and should not create any events for
      visits that fail QC validation.
    """
    # Arrange
    mock_logger = MockVisitEventCapture()
    event_accumulator = EventAccumulator(event_capture=mock_logger)
    mock_project = MockProjectAdaptor(
        label="ingest-form-mock", info={"pipeline_adcid": 2222}
    )

    # Create QC status file based on the JSON file using ErrorLogTemplate
    from error_logging.error_logger import ErrorLogTemplate

    forms_json = json_file.info["forms"]["json"]
    error_log_template = ErrorLogTemplate()
    qc_filename = error_log_template.instantiate(
        record=forms_json, module=forms_json["module"]
    )

    # Skip if ErrorLogTemplate can't generate filename
    if not qc_filename:
        return

    # Add QC status file to project
    mock_project.add_file(
        FileEntryFactory.create_mock_qc_status_file_for_project(
            filename=qc_filename,
            qc_status=qc_status,
        )
    )

    # Act
    event_accumulator.capture_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Events should only be created for PASS status
    if qc_status == QC_STATUS_PASS:
        assert len(mock_logger.logged_events) == 1, (
            f"Should create exactly one event for PASS status, "
            f"got {len(mock_logger.logged_events)}"
        )

        event = mock_logger.logged_events[0]
        assert_valid_qc_pass_event(
            event=event,
            expected_ptid=forms_json["ptid"],
            expected_visit_date=forms_json["visitdate"],
            expected_visit_number=forms_json["visitnum"],
            expected_module=forms_json["module"],
            expected_packet=forms_json.get("packet"),
        )
    else:
        assert len(mock_logger.logged_events) == 0, (
            f"Should not create events for non-PASS status {qc_status}, "
            f"got {len(mock_logger.logged_events)} events"
        )


@given(json_file=json_file_strategy())
@settings(max_examples=50)
def test_no_events_for_missing_qc_status(json_file: FileEntry):
    """Property test: No events created when QC status file is missing.

      **Feature: form-scheduler-event-logging-refactor,
    Property 1: QC-Pass Event Creation Only**
      **Validates: Requirements 1.1, 1.2**

      For any JSON file without a corresponding QC status file, no events should
      be created.
    """
    # Arrange
    mock_logger = MockVisitEventCapture()
    event_accumulator = EventAccumulator(event_capture=mock_logger)
    mock_project = MockProjectAdaptor(
        "ingest-form-mock"
    )  # Empty project with no QC status files

    # Act
    event_accumulator.capture_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - No events should be created
    assert len(mock_logger.logged_events) == 0, (
        f"Should not create events when QC status file is missing, "
        f"got {len(mock_logger.logged_events)} events"
    )


def test_qc_pass_event_structure():
    """Test that QC-pass events have the correct structure.

      **Feature: form-scheduler-event-logging-refactor,
    Property 1: QC-Pass Event Creation Only**
      **Validates: Requirements 1.1, 1.2**

      QC-pass events should have the correct action and all required fields.
    """
    # Arrange
    mock_logger = MockVisitEventCapture()
    event_accumulator = EventAccumulator(event_capture=mock_logger)
    mock_project = MockProjectAdaptor(
        label="ingest-form-mock", info={"pipeline_adcid": 1111}
    )

    # Create test JSON file
    json_file = Mock(spec=FileEntry)
    json_file.name = "test001_2024-01-15_uds.json"
    json_file.info = {
        "forms": {
            "json": {
                "ptid": "TEST001",
                "visitdate": "2024-01-15",
                "visitnum": "01",
                "module": "UDS",
                "packet": "I",
            }
        }
    }
    json_file.created = datetime.now()

    # Add PASS QC status file using ErrorLogTemplate generated name
    from error_logging.error_logger import ErrorLogTemplate

    error_log_template = ErrorLogTemplate()
    forms_json = json_file.info["forms"]["json"]
    expected_filename = error_log_template.instantiate(
        record=forms_json, module=forms_json["module"]
    )
    assert expected_filename is not None, "ErrorLogTemplate should generate a filename"
    mock_project.add_file(
        FileEntryFactory.create_mock_qc_status_file_for_project(
            filename=expected_filename,
            qc_status=QC_STATUS_PASS,
        )
    )

    # Act
    event_accumulator.capture_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]
    assert_valid_qc_pass_event(
        event=event,
        expected_ptid="TEST001",
        expected_visit_date="2024-01-15",
        expected_visit_number="01",
        expected_module="UDS",
        expected_packet="I",
    )


def test_multiple_json_files_mixed_qc_status():
    """Test multiple JSON files with mixed QC status outcomes.

      **Feature: form-scheduler-event-logging-refactor,
    Property 1: QC-Pass Event Creation Only**
      **Validates: Requirements 1.1, 1.2**

      Only JSON files with PASS QC status should generate events.
    """
    # Arrange
    mock_logger = MockVisitEventCapture()
    event_accumulator = EventAccumulator(event_capture=mock_logger)
    mock_project = MockProjectAdaptor(
        label="ingest-form-mock", info={"pipeline_adcid": 1111}
    )

    # Create test JSON files
    json_files = []
    expected_pass_count = 0

    for i, qc_status in enumerate(
        [QC_STATUS_PASS, "FAIL", QC_STATUS_PASS, "IN REVIEW"]
    ):
        json_file = Mock(spec=FileEntry)
        json_file.name = f"test{i:03d}_2024-01-15_uds.json"
        json_file.info = {
            "forms": {
                "json": {
                    "ptid": f"TEST{i:03d}",
                    "visitdate": "2024-01-15",
                    "visitnum": "01",
                    "module": "UDS",
                }
            }
        }
        json_file.created = datetime.now()
        json_files.append(json_file)

        # Add corresponding QC status file using ErrorLogTemplate
        from error_logging.error_logger import ErrorLogTemplate

        error_log_template = ErrorLogTemplate()
        forms_json = json_file.info["forms"]["json"]
        qc_filename = error_log_template.instantiate(
            record=forms_json, module=forms_json["module"]
        )
        assert qc_filename is not None, "ErrorLogTemplate should generate a filename"
        mock_project.add_file(
            FileEntryFactory.create_mock_qc_status_file_for_project(
                filename=qc_filename,
                qc_status=qc_status,
            )
        )

        if qc_status == QC_STATUS_PASS:
            expected_pass_count += 1

    # Act - Process each JSON file
    for json_file in json_files:
        event_accumulator.capture_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Only PASS files should generate events
    assert len(mock_logger.logged_events) == expected_pass_count, (
        f"Should create {expected_pass_count} events for PASS files, "
        f"got {len(mock_logger.logged_events)}"
    )

    # Assert - All logged events should be QC-pass events
    for event in mock_logger.logged_events:
        assert event.action == ACTION_PASS_QC, (
            f"All events should be QC-pass events, got {event.action}"
        )
