"""Property test for QC-pass event creation only.

**Feature: form-scheduler-event-logging-refactor, Property 1: QC-Pass Event Creation Only**
**Validates: Requirements 1.1, 1.2**
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from event_logging.event_logger import VisitEventLogger
from event_logging.visit_events import ACTION_PASS_QC, VisitEvent
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.simplified_event_accumulator import EventAccumulator
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import (
    QC_STATUS_PASS,
    GearQCModel,
    ValidationModel,
)


class MockVisitEventLogger(VisitEventLogger):
    """Mock VisitEventLogger for testing."""

    def __init__(self):
        self.logged_events: List[VisitEvent] = []

    def log_event(self, event: VisitEvent) -> None:
        """Mock log_event that stores events."""
        self.logged_events.append(event)


class MockProjectAdaptor:
    """Mock ProjectAdaptor for testing."""

    def __init__(self, label: str = "ingest-form-study001", group: str = "test-center"):
        self._label = label
        self._group = group
        self.files: Dict[str, FileEntry] = {}

    @property
    def label(self) -> str:
        return self._label

    @property
    def group(self) -> str:
        return self._group

    def get_pipeline_adcid(self) -> int:
        return 123

    def get_file(self, filename: str) -> Optional[FileEntry]:
        return self.files.get(filename)

    def add_qc_status_file(
        self,
        filename: str,
        qc_status: str,
        custom_info: Optional[Dict[str, Any]] = None,
    ) -> FileEntry:
        """Add a QC status file to the mock project."""
        # Create QC model with proper structure
        qc_data = {
            "test-gear": GearQCModel(
                validation=ValidationModel(
                    state=qc_status,
                    data=[],
                )
            )
        }

        # Create file entry
        file_entry = Mock(spec=FileEntry)
        file_entry.name = filename
        file_entry.modified = datetime.now()

        # Put QC data in custom info, not file contents
        file_entry.info = custom_info or {}
        file_entry.info["qc"] = qc_data

        self.files[filename] = file_entry
        return file_entry


@st.composite
def json_file_strategy(draw):
    """Generate random JSON file data."""
    ptid = draw(
        st.text(
            min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
    )
    # Generate dates with 4-digit years to match VisitEvent validation pattern
    visitdate = draw(
        st.dates(
            min_value=datetime(2000, 1, 1).date(),
            max_value=datetime(2030, 12, 31).date(),
        ).map(lambda d: d.strftime("%Y-%m-%d"))
    )
    visitnum = draw(st.text(min_size=1, max_size=3, alphabet="0123456789"))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD", "MDS"]))
    packet = draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"])))

    forms_json = {
        "ptid": ptid,
        "visitdate": visitdate,
        "visitnum": visitnum,
        "module": module,
    }
    if packet:
        forms_json["packet"] = packet

    file_entry = Mock(spec=FileEntry)
    file_entry.name = f"{ptid}_{visitdate}_{module.lower()}.json"
    file_entry.info = {"forms": {"json": forms_json}}
    file_entry.created = datetime.now()

    return file_entry


@st.composite
def qc_status_strategy(draw):
    """Generate QC status (PASS or non-PASS)."""
    return draw(st.sampled_from([QC_STATUS_PASS, "FAIL", "IN REVIEW"]))


@given(json_file=json_file_strategy(), qc_status=qc_status_strategy())
@settings(max_examples=100)
def test_qc_pass_event_creation_only(json_file: FileEntry, qc_status: str):
    """Property test: Only create QC-pass events for visits that pass QC
    validation.

    **Feature: form-scheduler-event-logging-refactor, Property 1: QC-Pass Event Creation Only**
    **Validates: Requirements 1.1, 1.2**

    For any pipeline completion, the system should create QC-pass events only for visits
    that pass QC validation and should not create any events for visits that fail QC validation.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger, datatype="form")
    mock_project = MockProjectAdaptor()

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
    mock_project.add_qc_status_file(qc_filename, qc_status)

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Events should only be created for PASS status
    if qc_status == QC_STATUS_PASS:
        assert len(mock_logger.logged_events) == 1, (
            f"Should create exactly one event for PASS status, got {len(mock_logger.logged_events)}"
        )

        event = mock_logger.logged_events[0]
        assert event.action == ACTION_PASS_QC, (
            f"Event action should be {ACTION_PASS_QC}, got {event.action}"
        )
        assert event.ptid == forms_json["ptid"], (
            f"Event PTID should match JSON file PTID {forms_json['ptid']}, got {event.ptid}"
        )
        assert event.module == forms_json["module"], (
            f"Event module should match JSON file module {forms_json['module']}, got {event.module}"
        )
    else:
        assert len(mock_logger.logged_events) == 0, (
            f"Should not create events for non-PASS status {qc_status}, got {len(mock_logger.logged_events)} events"
        )


@given(json_file=json_file_strategy())
@settings(max_examples=50)
def test_no_events_for_missing_qc_status(json_file: FileEntry):
    """Property test: No events created when QC status file is missing.

    **Feature: form-scheduler-event-logging-refactor, Property 1: QC-Pass Event Creation Only**
    **Validates: Requirements 1.1, 1.2**

    For any JSON file without a corresponding QC status file, no events should be created.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger, datatype="form")
    mock_project = MockProjectAdaptor()  # Empty project with no QC status files

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - No events should be created
    assert len(mock_logger.logged_events) == 0, (
        f"Should not create events when QC status file is missing, got {len(mock_logger.logged_events)} events"
    )


def test_qc_pass_event_structure():
    """Test that QC-pass events have the correct structure.

    **Feature: form-scheduler-event-logging-refactor, Property 1: QC-Pass Event Creation Only**
    **Validates: Requirements 1.1, 1.2**

    QC-pass events should have the correct action and all required fields.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger, datatype="form")
    mock_project = MockProjectAdaptor()

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
    mock_project.add_qc_status_file(expected_filename, QC_STATUS_PASS)

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]
    assert event.action == ACTION_PASS_QC, f"Event action should be {ACTION_PASS_QC}"
    assert event.datatype == "form", "Event datatype should be 'form'"
    assert event.gear_name == "form-scheduler", (
        "Event gear_name should be 'form-scheduler'"
    )
    assert event.ptid == "TEST001", "Event PTID should match"
    assert event.visit_date == "2024-01-15", "Event visit_date should match"
    assert event.visit_number == "01", "Event visit_number should match"
    assert event.module == "UDS", "Event module should match"
    assert event.packet == "I", "Event packet should match"
    assert event.pipeline_adcid == 123, "Event pipeline_adcid should match project"
    assert isinstance(event.timestamp, datetime), "Event timestamp should be datetime"


def test_multiple_json_files_mixed_qc_status():
    """Test multiple JSON files with mixed QC status outcomes.

    **Feature: form-scheduler-event-logging-refactor, Property 1: QC-Pass Event Creation Only**
    **Validates: Requirements 1.1, 1.2**

    Only JSON files with PASS QC status should generate events.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger, datatype="form")
    mock_project = MockProjectAdaptor()

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
        mock_project.add_qc_status_file(qc_filename, qc_status)

        if qc_status == QC_STATUS_PASS:
            expected_pass_count += 1

    # Act - Process each JSON file
    for json_file in json_files:
        event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Only PASS files should generate events
    assert len(mock_logger.logged_events) == expected_pass_count, (
        f"Should create {expected_pass_count} events for PASS files, got {len(mock_logger.logged_events)}"
    )

    # Assert - All logged events should be QC-pass events
    for event in mock_logger.logged_events:
        assert event.action == ACTION_PASS_QC, (
            f"All events should be QC-pass events, got {event.action}"
        )
