"""Tests for VisitEventAccumulator."""

from datetime import date, datetime
from typing import Dict, Tuple

import pytest
from configs.ingest_configs import ModuleConfigs
from event_logging.visit_event_accumulator import (
    PendingVisitData,
    VisitEventAccumulator,
)
from flywheel import Project
from flywheel.models.file_entry import FileEntry
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_event_logging import MockVisitEventLogger
from test_mocks.mock_flywheel import (
    MockAcquisition,
    MockFile,
    MockFlywheelProxy,
    MockParents,
    MockSession,
    create_mock_file_with_parent,
)


@pytest.fixture
def mock_event_logger() -> MockVisitEventLogger:
    """Create mock event logger."""
    return MockVisitEventLogger()


@pytest.fixture
def mock_proxy() -> MockFlywheelProxy:
    """Create mock Flywheel proxy."""
    return MockFlywheelProxy()


@pytest.fixture
def module_configs() -> Dict[str, ModuleConfigs]:
    """Create module configs dict."""

    return {"UDS": uds_ingest_configs()}


@pytest.fixture
def mock_project() -> Project:
    """Create mock project."""
    project = Project(label="ingest-form-alpha", group="alpha")
    project.info = {"pipeline_adcid": 42}
    return project


@pytest.fixture
def accumulator(
    mock_event_logger: MockVisitEventLogger,
    module_configs: Dict[str, ModuleConfigs],
    mock_proxy: MockFlywheelProxy,
) -> VisitEventAccumulator:
    """Create VisitEventAccumulator instance."""
    return VisitEventAccumulator(
        event_logger=mock_event_logger,  # type: ignore[arg-type]
        module_configs=module_configs,
        proxy=mock_proxy,
    )


class TestPendingVisitData:
    """Tests for PendingVisitData model."""

    def test_create_pending_visit_data(self) -> None:
        """Test creating PendingVisitData."""
        data = PendingVisitData(
            visit_number="01",
            session_id="session-123",
            acquisition_id="acq-456",
            module="UDS",
            project_label="ingest-form-alpha",
            center_label="alpha",
            pipeline_adcid=42,
            upload_timestamp=datetime(2024, 1, 15, 10, 0, 0),
        )

        assert data.visit_number == "01"
        assert data.session_id == "session-123"
        assert data.acquisition_id == "acq-456"
        assert data.module == "UDS"
        assert data.project_label == "ingest-form-alpha"
        assert data.center_label == "alpha"
        assert data.pipeline_adcid == 42
        assert data.upload_timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert data.completion_timestamp is None
        assert data.csv_filename == ""


class TestVisitEventAccumulator:
    """Tests for VisitEventAccumulator."""

    def setup_containers(
        self,
        mock_proxy: MockFlywheelProxy,
        visit_number: str = "01",
        session_label: str = "FORMS-VISIT-01",
    ) -> Tuple[MockSession, MockAcquisition, FileEntry]:
        """Set up mock containers for testing.

        Args:
            mock_proxy: Mock Flywheel proxy
            visit_number: Visit number
            session_label: Session label

        Returns:
            Tuple of (session, acquisition, file)
        """
        # Create session
        session = MockSession(
            id="session-123",
            label=session_label,
            parents=MockParents(subject="subject-789", project="project-000"),
        )

        # Create acquisition
        acquisition = MockAcquisition(
            id="acq-456",
            label="UDS",
            parents=MockParents(
                session="session-123",
                subject="subject-789",
                project="project-000",
            ),
            files=[],
        )

        # Create file
        file = create_mock_file_with_parent(
            name="test.csv",
            parent_id="acq-456",
            created=datetime(2024, 1, 15, 10, 0, 0),
        )

        # Add containers to proxy
        mock_proxy.add_container("session-123", session)
        mock_proxy.add_container("acq-456", acquisition)

        return session, acquisition, file

    def test_record_file_queued_success(
        self, accumulator, mock_proxy, mock_project
    ) -> None:
        """Test successfully recording a queued file."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Check that pending data was stored
        assert "01" in accumulator.pending
        pending = accumulator.pending["01"]

        assert pending.visit_number == "01"
        assert pending.session_id == "session-123"
        assert pending.acquisition_id == "acq-456"
        assert pending.module == "UDS"
        assert pending.project_label == "ingest-form-alpha"
        assert pending.center_label == "alpha"
        assert pending.pipeline_adcid == 42
        assert pending.upload_timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert pending.csv_filename == "test.csv"

    def test_record_file_queued_invalid_session_label(
        self, accumulator, mock_proxy, mock_project
    ):
        """Test recording file with invalid session label."""
        session, acquisition, file = self.setup_containers(
            mock_proxy, session_label="INVALID-LABEL"
        )

        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_record_file_queued_missing_pipeline_adcid(
        self, accumulator, mock_proxy
    ) -> None:
        """Test recording file when project missing pipeline_adcid."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create project without pipeline_adcid
        project = Project(label="ingest-form-alpha", group="alpha")
        project.info = {}

        accumulator.record_file_queued(file=file, module="UDS", project=project)

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_record_file_queued_unknown_module(
        self, accumulator, mock_proxy, mock_project
    ):
        """Test recording file with unknown module."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        accumulator.record_file_queued(
            file=file, module="UNKNOWN", project=mock_project
        )

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_finalize_and_log_events_success(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test successfully finalizing and logging events."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create JSON file with metadata
        json_file = MockFile(
            name="110001_FORMS-VISIT-01_UDS.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        "visitnum": "01",
                        "visitdate": "2024-01-15",
                        "packet": "I",
                        "module": "UDS",
                    }
                },
                "qc": {
                    "form-screening": {"validation": {"state": "PASS"}},
                    "form-transformer": {"validation": {"state": "PASS"}},
                    "form-qc-checker": {"validation": {"state": "PASS"}},
                },
            },
        )
        acquisition.files = [json_file]

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then finalize and log events
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # Check that events were logged
        assert len(mock_event_logger.logged_events) == 2

        # Check submit event
        submit_events = mock_event_logger.get_events_by_action("submit")
        assert len(submit_events) == 1
        submit_event = submit_events[0]
        assert submit_event.action == "submit"
        assert submit_event.ptid == "110001"
        assert submit_event.visit_number == "01"
        assert submit_event.visit_date == date(2024, 1, 15)
        assert submit_event.module == "UDS"
        assert submit_event.packet == "I"
        assert submit_event.pipeline_adcid == 42
        assert submit_event.project_label == "ingest-form-alpha"
        assert submit_event.center_label == "alpha"
        assert submit_event.gear_name == "form-scheduler"
        assert submit_event.datatype == "form"
        assert submit_event.timestamp == datetime(2024, 1, 15, 10, 0, 0)

        # Check pass-qc event
        pass_qc_events = mock_event_logger.get_events_by_action("pass-qc")
        assert len(pass_qc_events) == 1
        pass_qc_event = pass_qc_events[0]
        assert pass_qc_event.action == "pass-qc"
        assert pass_qc_event.ptid == "110001"
        assert pass_qc_event.visit_number == "01"
        assert pass_qc_event.visit_date == date(2024, 1, 15)
        assert pass_qc_event.module == "UDS"
        assert pass_qc_event.packet == "I"
        # Completion timestamp should be different from upload timestamp
        assert pass_qc_event.timestamp != submit_event.timestamp

        # Check that pending data was cleaned up
        assert len(accumulator.pending) == 0

    def test_finalize_and_log_events_failure(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test finalizing and logging events when pipeline fails."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create JSON file with metadata
        json_file = MockFile(
            name="110001_FORMS-VISIT-01_UDS.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        "visitnum": "01",
                        "visitdate": "2024-01-15",
                        "packet": "I",
                        "module": "UDS",
                    }
                },
                "qc": {
                    "form-screening": {"validation": {"state": "FAIL"}},
                },
            },
        )
        acquisition.files = [json_file]

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then finalize and log events with failure
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=False
        )

        # Check that events were logged
        assert len(mock_event_logger.logged_events) == 2

        # Check submit event
        submit_events = mock_event_logger.get_events_by_action("submit")
        assert len(submit_events) == 1

        # Check not-pass-qc event
        not_pass_qc_events = mock_event_logger.get_events_by_action("not-pass-qc")
        assert len(not_pass_qc_events) == 1
        not_pass_qc_event = not_pass_qc_events[0]
        assert not_pass_qc_event.action == "not-pass-qc"
        assert not_pass_qc_event.ptid == "110001"

        # Check that pending data was cleaned up
        assert len(accumulator.pending) == 0

    def test_finalize_and_log_events_no_pending_data(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test finalizing when no pending data exists (re-evaluation
        scenario).

        This represents cases where visits are re-evaluated without a new
        submission, such as:
        - QC alerts approved after initial failure
        - Dependency resolution (e.g., UDS packet cleared)

        Current behavior: No events logged (returns early)
        Future enhancement: Should log outcome event only (no submit event)
        """
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Don't record file as queued, just try to finalize
        # This simulates a re-evaluation scenario
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # Current behavior: No events should be logged
        # TODO: When re-evaluation support is added, this should log
        # a "pass-qc" event without a "submit" event
        assert len(mock_event_logger.logged_events) == 0

    def test_finalize_and_log_events_no_json_file(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test finalizing when JSON file is missing."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # No JSON file in acquisition
        acquisition.files = []

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then try to finalize
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # No events should be logged
        assert len(mock_event_logger.logged_events) == 0

        # Pending data should be cleaned up
        assert len(accumulator.pending) == 0

    def test_finalize_and_log_events_missing_metadata(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test finalizing when JSON file missing required metadata."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create JSON file with incomplete metadata
        json_file = MockFile(
            name="110001_FORMS-VISIT-01_UDS.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        # Missing visitnum and visitdate
                        "packet": "I",
                        "module": "UDS",
                    }
                }
            },
        )
        acquisition.files = [json_file]

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then try to finalize
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # No events should be logged
        assert len(mock_event_logger.logged_events) == 0

        # Pending data should be cleaned up
        assert len(accumulator.pending) == 0

    def test_finalize_and_log_events_multiple_json_files(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test finalizing when multiple JSON files exist."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create multiple JSON files
        json_file_uds = MockFile(
            name="110001_FORMS-VISIT-01_UDS.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        "visitnum": "01",
                        "visitdate": "2024-01-15",
                        "packet": "I",
                        "module": "UDS",
                    }
                }
            },
        )
        json_file_other = MockFile(
            name="110001_FORMS-VISIT-01_OTHER.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        "visitnum": "01",
                        "visitdate": "2024-01-15",
                        "packet": "I",
                        "module": "OTHER",
                    }
                }
            },
        )
        acquisition.files = [json_file_other, json_file_uds]

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then finalize - should find UDS file
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # Events should be logged
        assert len(mock_event_logger.logged_events) == 2

        # Check that UDS module was used
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.module == "UDS"

    def test_extract_visit_number_different_formats(
        self, accumulator, mock_proxy, mock_project
    ):
        """Test extracting visit numbers from different session label
        formats."""
        # Test with visit 01
        session1, acquisition1, file1 = self.setup_containers(
            mock_proxy, visit_number="01", session_label="FORMS-VISIT-01"
        )
        accumulator.record_file_queued(file=file1, module="UDS", project=mock_project)
        assert "01" in accumulator.pending

        # Clear pending
        accumulator.pending.clear()

        # Test with visit 10
        session2, acquisition2, file2 = self.setup_containers(
            mock_proxy, visit_number="10", session_label="FORMS-VISIT-10"
        )
        # Update container IDs to avoid conflicts
        session2.id = "session-124"
        acquisition2.id = "acq-457"
        acquisition2.parents.session = "session-124"
        file2.parent_ref.id = "acq-457"
        mock_proxy.add_container("session-124", session2)
        mock_proxy.add_container("acq-457", acquisition2)

        accumulator.record_file_queued(file=file2, module="UDS", project=mock_project)
        assert "10" in accumulator.pending

    def test_packet_optional(
        self, accumulator, mock_proxy, mock_project, mock_event_logger
    ):
        """Test that packet field is optional."""
        session, acquisition, file = self.setup_containers(mock_proxy)

        # Create JSON file without packet
        json_file = MockFile(
            name="110001_FORMS-VISIT-01_UDS.json",
            info={
                "forms": {
                    "json": {
                        "ptid": "110001",
                        "visitnum": "01",
                        "visitdate": "2024-01-15",
                        "module": "UDS",
                        # No packet field
                    }
                }
            },
        )
        acquisition.files = [json_file]

        # First record the file as queued
        accumulator.record_file_queued(file=file, module="UDS", project=mock_project)

        # Then finalize and log events
        accumulator.finalize_and_log_events(
            file=file, module="UDS", pipeline_succeeded=True
        )

        # Events should be logged with packet=None
        assert len(mock_event_logger.logged_events) == 2
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.packet is None
