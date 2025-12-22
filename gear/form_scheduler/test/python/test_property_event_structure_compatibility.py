"""Property test for event structure compatibility.

**Feature: form-scheduler-event-logging-refactor, Property 10: Event Structure
Compatibility**
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
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
    VisitMetadata,
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
        qc_completion_time: Optional[datetime] = None,
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
        file_entry.modified = qc_completion_time or datetime.now()

        # Put QC data in custom info, not file contents
        file_entry.info = custom_info or {}
        file_entry.info["qc"] = qc_data

        self.files[filename] = file_entry
        return file_entry


@st.composite
def visit_metadata_strategy(draw):
    """Generate random VisitMetadata for QC status custom info."""
    ptid = draw(
        st.text(
            min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
    )
    # Generate dates with 4-digit years to match VisitEvent validation pattern
    date = draw(
        st.dates(
            min_value=datetime(2000, 1, 1).date(),
            max_value=datetime(2030, 12, 31).date(),
        ).map(lambda d: d.strftime("%Y-%m-%d"))
    )
    visitnum = draw(st.text(min_size=1, max_size=3, alphabet="0123456789"))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD", "MDS"]))
    packet = draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"])))

    return VisitMetadata(
        ptid=ptid,
        date=date,
        visitnum=visitnum,
        module=module,
        packet=packet,
    )


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


@given(
    visit_metadata=visit_metadata_strategy(),
    qc_completion_time=st.datetimes(
        min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)
    ),
)
@settings(max_examples=100)
def test_event_structure_compatibility(
    visit_metadata: VisitMetadata, qc_completion_time: datetime
):
    """Property test: QC-pass events maintain compatible structure and field
    names.

    **Feature: form-scheduler-event-logging-refactor, Property 10: Event
    Structure Compatibility**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

    For any QC-pass event created, the event should maintain the same structure,
    field names, S3 storage conventions, timestamp source (QC completion time),
    required metadata fields, and gear name ("form-scheduler") as the previous
    implementation.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger)
    mock_project = MockProjectAdaptor()

    # Create JSON file from visit metadata
    json_file = Mock(spec=FileEntry)
    assert visit_metadata.module, "module is required for visit metadata"
    json_file.name = (
        f"{visit_metadata.ptid}_{visit_metadata.date}_"
        f"{visit_metadata.module.lower()}.json"
    )
    forms_json = {
        "ptid": visit_metadata.ptid,
        "visitdate": visit_metadata.date,
        "visitnum": visit_metadata.visitnum,
        "module": visit_metadata.module,
    }
    if visit_metadata.packet:
        forms_json["packet"] = visit_metadata.packet

    json_file.info = {"forms": {"json": forms_json}}
    json_file.created = datetime.now()

    # Create QC status file with visit metadata in custom info
    from error_logging.error_logger import ErrorLogTemplate

    error_log_template = ErrorLogTemplate()
    assert visit_metadata.module, "visit_metadata module is required"
    qc_filename = error_log_template.instantiate(
        record=forms_json, module=visit_metadata.module
    )

    # Skip if ErrorLogTemplate can't generate filename
    if not qc_filename:
        return

    # Add QC status file with visit metadata in custom info
    custom_info = {"visit": visit_metadata.model_dump(exclude_none=True, mode="raw")}
    mock_project.add_qc_status_file(
        qc_filename, QC_STATUS_PASS, custom_info, qc_completion_time
    )

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Event structure compatibility
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]

    # Requirement 6.1: Same event structure and field names
    assert hasattr(event, "action"), "Event should have 'action' field"
    assert hasattr(event, "study"), "Event should have 'study' field"
    assert hasattr(event, "pipeline_adcid"), "Event should have 'pipeline_adcid' field"
    assert hasattr(event, "project_label"), "Event should have 'project_label' field"
    assert hasattr(event, "center_label"), "Event should have 'center_label' field"
    assert hasattr(event, "gear_name"), "Event should have 'gear_name' field"
    assert hasattr(event, "ptid"), "Event should have 'ptid' field"
    assert hasattr(event, "visit_date"), "Event should have 'visit_date' field"
    assert hasattr(event, "visit_number"), "Event should have 'visit_number' field"
    assert hasattr(event, "datatype"), "Event should have 'datatype' field"
    assert hasattr(event, "module"), "Event should have 'module' field"
    assert hasattr(event, "packet"), "Event should have 'packet' field"
    assert hasattr(event, "timestamp"), "Event should have 'timestamp' field"

    # Requirement 6.3: QC completion time as timestamp
    assert event.timestamp == qc_completion_time, (
        f"Event timestamp should be QC completion time "
        f"{qc_completion_time}, got {event.timestamp}"
    )

    # Requirement 6.4: All required metadata fields preserved
    assert event.ptid == visit_metadata.ptid, (
        f"Event PTID should match visit metadata {visit_metadata.ptid}, "
        f"got {event.ptid}"
    )
    assert event.visit_date == visit_metadata.date, (
        f"Event visit_date should match visit metadata date "
        f"{visit_metadata.date}, got {event.visit_date}"
    )
    assert event.visit_number == visit_metadata.visitnum, (
        f"Event visit_number should match visit metadata visitnum "
        f"{visit_metadata.visitnum}, got {event.visit_number}"
    )
    assert event.module == visit_metadata.module, (
        f"Event module should match visit metadata {visit_metadata.module}, "
        f"got {event.module}"
    )
    assert event.packet == visit_metadata.packet, (
        f"Event packet should match visit metadata {visit_metadata.packet}, "
        f"got {event.packet}"
    )

    # Requirement 6.5: Gear name is "form-scheduler"
    assert event.gear_name == "form-scheduler", (
        f"Event gear_name should be 'form-scheduler', got {event.gear_name}"
    )

    # Additional structure validation
    assert event.action == ACTION_PASS_QC, (
        f"Event action should be {ACTION_PASS_QC}, got {event.action}"
    )
    assert event.datatype == "form", (
        f"Event datatype should be 'form', got {event.datatype}"
    )
    assert event.pipeline_adcid == 123, (
        f"Event pipeline_adcid should match project value 123, "
        f"got {event.pipeline_adcid}"
    )
    assert event.project_label == "ingest-form-study001", (
        f"Event project_label should match project label, got {event.project_label}"
    )
    assert event.center_label == "test-center", (
        f"Event center_label should match project group, got {event.center_label}"
    )


@given(json_file=json_file_strategy())
@settings(max_examples=50)
def test_event_structure_with_json_fallback(json_file: FileEntry):
    """Property test: Event structure compatibility when using JSON file
    fallback.

    **Feature: form-scheduler-event-logging-refactor, Property 10: Event
    Structure Compatibility**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

    Events created from JSON file metadata (fallback) should have the same structure
    as events created from QC status custom info.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger)
    mock_project = MockProjectAdaptor()

    # Create QC status file WITHOUT visit metadata in custom info (forces JSON fallback)
    from error_logging.error_logger import ErrorLogTemplate

    forms_json = json_file.info["forms"]["json"]
    error_log_template = ErrorLogTemplate()
    qc_filename = error_log_template.instantiate(
        record=forms_json, module=forms_json["module"]
    )

    # Skip if ErrorLogTemplate can't generate filename
    if not qc_filename:
        return

    # Add QC status file without visit metadata (empty custom info)
    qc_completion_time = datetime.now()
    mock_project.add_qc_status_file(qc_filename, QC_STATUS_PASS, {}, qc_completion_time)

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Event structure should be the same even with JSON fallback
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]

    # Same structure validation as above
    assert event.action == ACTION_PASS_QC, "Event action should be pass-qc"
    assert event.gear_name == "form-scheduler", (
        "Event gear_name should be 'form-scheduler'"
    )
    assert event.datatype == "form", "Event datatype should be 'form'"
    assert event.ptid == forms_json["ptid"], "Event PTID should match JSON file"
    assert event.visit_date == forms_json["visitdate"], (
        "Event visit_date should match JSON file"
    )
    assert event.visit_number == forms_json["visitnum"], (
        "Event visit_number should match JSON file"
    )
    assert event.module == forms_json["module"], "Event module should match JSON file"
    assert event.packet == forms_json.get("packet"), (
        "Event packet should match JSON file"
    )
    assert event.timestamp == qc_completion_time, (
        "Event timestamp should be QC completion time"
    )


def test_event_structure_required_fields():
    """Test that events contain all required fields for backward compatibility.

    **Feature: form-scheduler-event-logging-refactor, Property 10: Event
    Structure Compatibility**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

    Events must contain all fields that downstream consumers expect.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger)
    mock_project = MockProjectAdaptor()

    # Create test JSON file with all fields
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

    # Add QC status file
    from error_logging.error_logger import ErrorLogTemplate

    error_log_template = ErrorLogTemplate()
    forms_json = json_file.info["forms"]["json"]
    qc_filename = error_log_template.instantiate(
        record=forms_json, module=forms_json["module"]
    )
    assert qc_filename is not None, "ErrorLogTemplate should generate a filename"

    qc_completion_time = datetime(2024, 1, 15, 10, 30, 0)
    mock_project.add_qc_status_file(qc_filename, QC_STATUS_PASS, {}, qc_completion_time)

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - All required fields present with correct values
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]

    # Required fields for backward compatibility
    required_fields = [
        "action",
        "study",
        "pipeline_adcid",
        "project_label",
        "center_label",
        "gear_name",
        "ptid",
        "visit_date",
        "visit_number",
        "datatype",
        "module",
        "packet",
        "timestamp",
    ]

    for field in required_fields:
        assert hasattr(event, field), f"Event must have required field '{field}'"

    # Verify specific values for compatibility
    assert event.action == ACTION_PASS_QC, "Action must be 'pass-qc'"
    assert event.gear_name == "form-scheduler", "Gear name must be 'form-scheduler'"
    assert event.datatype == "form", "Datatype must be 'form'"
    assert isinstance(event.timestamp, datetime), "Timestamp must be datetime object"
    assert isinstance(event.pipeline_adcid, int), "Pipeline ADCID must be integer"


def test_event_structure_s3_storage_compatibility():
    """Test that events are structured for S3 storage compatibility.

    **Feature: form-scheduler-event-logging-refactor, Property 10: Event
    Structure Compatibility**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

    Events should be serializable and contain the structure expected by S3 storage.
    """
    # Arrange
    mock_logger = MockVisitEventLogger()
    event_accumulator = EventAccumulator(event_logger=mock_logger)
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

    # Add QC status file
    from error_logging.error_logger import ErrorLogTemplate

    error_log_template = ErrorLogTemplate()
    forms_json = json_file.info["forms"]["json"]
    qc_filename = error_log_template.instantiate(
        record=forms_json, module=forms_json["module"]
    )
    assert qc_filename is not None, "ErrorLogTemplate should generate a filename"

    mock_project.add_qc_status_file(qc_filename, QC_STATUS_PASS)

    # Act
    event_accumulator.log_events(json_file, mock_project)  # type: ignore[arg-type]

    # Assert - Event should be serializable (test JSON serialization)
    assert len(mock_logger.logged_events) == 1, "Should create exactly one event"

    event = mock_logger.logged_events[0]

    # Test that event can be serialized (important for S3 storage)
    try:
        event_dict = event.model_dump()
        assert isinstance(event_dict, dict), "Event should serialize to dictionary"

        # Verify key fields are present in serialized form
        assert "action" in event_dict, "Serialized event should contain 'action'"
        assert "gear_name" in event_dict, "Serialized event should contain 'gear_name'"
        assert "ptid" in event_dict, "Serialized event should contain 'ptid'"
        assert "timestamp" in event_dict, "Serialized event should contain 'timestamp'"

        # Verify values are correct in serialized form
        assert event_dict["action"] == ACTION_PASS_QC, (
            "Serialized action should be 'pass-qc'"
        )
        assert event_dict["gear_name"] == "form-scheduler", (
            "Serialized gear_name should be 'form-scheduler'"
        )

    except Exception as e:
        raise AssertionError(
            f"Event should be serializable for S3 storage, but got error: {e}"
        ) from e
