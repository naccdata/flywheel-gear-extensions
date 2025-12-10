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
            ptid="110001",
            visit_date="2024-01-15",
            visit_number="01",
            session_id="session-123",
            acquisition_id="acq-456",
            module="UDS",
            project_label="ingest-form-alpha",
            center_label="alpha",
            pipeline_adcid=42,
            upload_timestamp=datetime(2024, 1, 15, 10, 0, 0),
        )

        assert data.ptid == "110001"
        assert data.visit_date == "2024-01-15"
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
        add_project: bool = False,
        add_qc_log: bool = False,
        add_json: bool = False,
    ) -> Tuple[MockSession, MockAcquisition, FileEntry, Project]:
        """Set up mock containers for testing.

        Args:
            mock_proxy: Mock Flywheel proxy
            visit_number: Visit number
            session_label: Session label
            add_project: Whether to add project container to proxy
            add_qc_log: Whether to add QC log file at PROJECT level
            add_json: Whether to add JSON file at ACQUISITION level

        Returns:
            Tuple of (session, acquisition, csv_file, project)
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

        # Add containers to proxy
        mock_proxy.add_container("session-123", session)
        mock_proxy.add_container("acq-456", acquisition)

        # Create project
        mock_project_obj = Project(label="ingest-form-alpha", group="alpha")
        mock_project_obj.info = {"pipeline_adcid": 42}
        mock_project_obj.files = []

        # Create CSV file at PROJECT level
        csv_file = create_mock_file_with_parent(
            name="test.csv",
            parent_id="project-000",
            created=datetime(2024, 1, 15, 10, 0, 0),
        )

        # Optionally add QC log file at PROJECT level
        if add_qc_log:
            qc_log_file = MockFile(
                name="110001_2024-01-15_UDS_qc-status.log",
                info={
                    "ptid": "110001",
                    "visitdate": "2024-01-15",
                    "visitnum": "01",
                    "packet": "I",
                    "module": "UDS",
                },
            )
            mock_project_obj.files.append(qc_log_file)

        # Optionally add JSON file at ACQUISITION level
        if add_json:
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
                },
            )
            acquisition.files.append(json_file)

        # Add project to proxy if requested
        if add_project:
            mock_proxy.add_container("project-000", mock_project_obj)

        return session, acquisition, csv_file, mock_project_obj

    def test_record_file_queued_no_metadata(
        self, accumulator, mock_proxy, mock_event_logger
    ) -> None:
        """Test recording queued file when no metadata exists yet.

        Scenario 1: CSV at PROJECT level only
        - No QC log at PROJECT level
        - No JSON at ACQUISITION level

        Expected: Temp key created, no submit event logged yet
        """
        from event_logging.visit_event_accumulator import VisitKey

        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Check that pending data was stored with temp key
        temp_key = VisitKey(ptid="temp_01", visit_date="", module="UDS")
        assert temp_key in accumulator.pending
        pending = accumulator.pending[temp_key]

        assert pending.visit_number == "01"
        assert pending.session_id == "session-123"
        assert pending.acquisition_id == "acq-456"
        assert pending.module == "UDS"
        assert pending.project_label == "ingest-form-alpha"
        assert pending.center_label == "alpha"
        assert pending.pipeline_adcid == 42
        assert pending.upload_timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert pending.csv_filename == "test.csv"
        assert pending.submit_logged is False

        # No submit event logged yet
        assert len(mock_event_logger.logged_events) == 0

    def test_record_file_queued_with_qc_log(
        self, accumulator, mock_proxy, mock_event_logger
    ) -> None:
        """Test recording queued file when QC log exists.

        Scenario 2: CSV at PROJECT level + QC log at PROJECT level
        - QC log exists (created by identifier-lookup)
        - No JSON at ACQUISITION level yet

        Expected: Submit event logged immediately using QC log metadata
        """
        from event_logging.visit_event_accumulator import VisitKey

        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True, add_qc_log=True
        )

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Check that pending data was stored with proper key
        key = VisitKey(ptid="110001", visit_date="2024-01-15", module="UDS")
        assert key in accumulator.pending
        pending = accumulator.pending[key]

        assert pending.ptid == "110001"
        assert pending.visit_date == "2024-01-15"
        assert pending.visit_number == "01"
        assert pending.submit_logged is True

        # Submit event should be logged
        assert len(mock_event_logger.logged_events) == 1
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.ptid == "110001"
        assert submit_event.visit_date == date(2024, 1, 15)
        assert submit_event.module == "UDS"

    def test_record_file_queued_with_json(
        self, accumulator, mock_proxy, mock_event_logger
    ) -> None:
        """Test recording queued file when JSON exists.

        Scenario 3: CSV at PROJECT level + JSON at ACQUISITION level
        - No QC log at PROJECT level
        - JSON exists at ACQUISITION level

        Expected: Submit event logged immediately using JSON metadata
        """
        from event_logging.visit_event_accumulator import VisitKey

        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True, add_json=True
        )

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Check that pending data was stored with proper key
        key = VisitKey(ptid="110001", visit_date="2024-01-15", module="UDS")
        assert key in accumulator.pending
        pending = accumulator.pending[key]

        assert pending.ptid == "110001"
        assert pending.visit_date == "2024-01-15"
        assert pending.visit_number == "01"
        assert pending.submit_logged is True

        # Submit event should be logged
        assert len(mock_event_logger.logged_events) == 1
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.ptid == "110001"

    def test_record_file_queued_qc_log_preferred_over_json(
        self, accumulator, mock_proxy, mock_event_logger
    ) -> None:
        """Test that QC log is preferred over JSON when both exist.

        Scenario 4: CSV at PROJECT level + QC log at PROJECT level + JSON at ACQUISITION level
        - Both QC log and JSON exist

        Expected: QC log is used (more reliable), submit event logged
        """
        from event_logging.visit_event_accumulator import VisitKey

        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True, add_qc_log=True, add_json=True
        )

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Check that pending data was stored
        key = VisitKey(ptid="110001", visit_date="2024-01-15", module="UDS")
        assert key in accumulator.pending

        # Submit event should be logged
        assert len(mock_event_logger.logged_events) == 1

    def test_record_file_queued_invalid_session_label(self, accumulator, mock_proxy):
        """Test recording file with invalid session label."""
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, session_label="INVALID-LABEL", add_project=True
        )

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_record_file_queued_missing_pipeline_adcid(
        self, accumulator, mock_proxy
    ) -> None:
        """Test recording file when project missing pipeline_adcid."""
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Remove pipeline_adcid
        project.info = {}

        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_record_file_queued_unknown_module(self, accumulator, mock_proxy):
        """Test recording file with unknown module."""
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        accumulator.record_file_queued(file=csv_file, module="UNKNOWN", project=project)

        # Should not store pending data
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_deferred_submit(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome when submit was deferred.

        Setup:
        - At queue time: CSV only (no metadata)
        - At completion: CSV + JSON at ACQUISITION level

        Expected: Submit event logged during log_outcome_event (deferred)
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # No submit event yet
        assert len(mock_event_logger.logged_events) == 0

        # Now add JSON file (simulating pipeline creating it)
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
            },
        )
        acquisition.files = [json_file]

        # Log outcome event
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # Check that both events were logged
        assert len(mock_event_logger.logged_events) == 2

        # Check submit event (deferred)
        submit_events = mock_event_logger.get_events_by_action("submit")
        assert len(submit_events) == 1
        submit_event = submit_events[0]
        assert submit_event.ptid == "110001"
        assert submit_event.timestamp == datetime(2024, 1, 15, 10, 0, 0)

        # Check pass-qc event
        pass_qc_events = mock_event_logger.get_events_by_action("pass-qc")
        assert len(pass_qc_events) == 1
        pass_qc_event = pass_qc_events[0]
        assert pass_qc_event.ptid == "110001"
        assert pass_qc_event.timestamp != submit_event.timestamp

        # Pending data cleaned up
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_immediate_submit(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome when submit was immediate.

        Setup:
        - At queue time: CSV + QC log at PROJECT level
        - At completion: CSV + QC log + JSON at ACQUISITION level

        Expected: Only outcome event logged (submit already logged at queue time)
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True, add_qc_log=True
        )

        # Queue file with QC log - submit event logged immediately
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Submit event already logged
        assert len(mock_event_logger.logged_events) == 1

        # Add JSON file (created by pipeline)
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
            },
        )
        acquisition.files = [json_file]

        # Log outcome event
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # Check that only outcome event was added (total 2 events)
        assert len(mock_event_logger.logged_events) == 2

        # Check pass-qc event
        pass_qc_events = mock_event_logger.get_events_by_action("pass-qc")
        assert len(pass_qc_events) == 1

        # Pending data cleaned up
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_failure(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome event when pipeline fails.

        Setup:
        - At queue time: CSV only
        - At completion: CSV + JSON at ACQUISITION level

        Expected: Submit + not-pass-qc events logged
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Add JSON file
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
            },
        )
        acquisition.files = [json_file]

        # Log outcome with failure
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=False
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

        # Pending data cleaned up
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_no_pending_data(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome event when no pending data exists (re-
        evaluation).

        Setup:
        - CSV at PROJECT level
        - JSON at ACQUISITION level
        - No pending data (record_file_queued not called)

        This represents re-evaluation scenarios:
        - QC alerts approved after initial failure
        - Dependency resolution (e.g., UDS packet cleared)

        Current behavior: No events logged (returns early)
        Future: Should log outcome event only (no submit event)
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True, add_json=True
        )

        # Don't call record_file_queued - simulates re-evaluation
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # Current behavior: No events logged
        # TODO: Support re-evaluation by logging outcome event only
        assert len(mock_event_logger.logged_events) == 0

    def test_log_outcome_event_no_json_file(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome when pipeline fails before creating JSON.

        Setup:
        - At queue time: CSV only
        - At completion: CSV only (no JSON, no QC log)

        Represents: Pipeline failed at identifier-lookup or form-transformer
        Expected: No events logged, pending data cleaned up
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Try to log outcome with no JSON created
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # No events should be logged
        assert len(mock_event_logger.logged_events) == 0

        # Pending data should be cleaned up
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_missing_metadata(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome when JSON has incomplete metadata.

        Setup:
        - At queue time: CSV only
        - At completion: CSV + malformed JSON at ACQUISITION level

        Represents: Malformed JSON file (missing required fields)
        Expected: No events logged, pending data cleaned up
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Add JSON file with incomplete metadata
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

        # Try to log outcome
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # No events should be logged
        assert len(mock_event_logger.logged_events) == 0

        # Pending data should be cleaned up
        assert len(accumulator.pending) == 0

    def test_log_outcome_event_multiple_json_files(
        self, accumulator, mock_proxy, mock_event_logger
    ):
        """Test logging outcome when multiple JSON files exist.

        Setup:
        - At queue time: CSV only
        - At completion: CSV + multiple JSON files at ACQUISITION level

        Expected: Correct module-specific JSON file is selected
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Add multiple JSON files
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

        # Log outcome - should find UDS file
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # Events should be logged
        assert len(mock_event_logger.logged_events) == 2

        # Check that UDS module was used
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.module == "UDS"

    def test_extract_visit_number_different_formats(self, accumulator, mock_proxy):
        """Test extracting visit numbers from different session label formats.

        Setup: CSV at PROJECT level with different session labels
        Expected: Visit numbers correctly extracted from session labels
        """
        from event_logging.visit_event_accumulator import VisitKey

        # Test with visit 01
        session1, acquisition1, csv_file1, project1 = self.setup_containers(
            mock_proxy,
            visit_number="01",
            session_label="FORMS-VISIT-01",
            add_project=True,
        )
        accumulator.record_file_queued(file=csv_file1, module="UDS", project=project1)
        temp_key_01 = VisitKey(ptid="temp_01", visit_date="", module="UDS")
        assert temp_key_01 in accumulator.pending

        # Clear pending
        accumulator.pending.clear()

        # Test with visit 10
        session2, acquisition2, csv_file2, project2 = self.setup_containers(
            mock_proxy,
            visit_number="10",
            session_label="FORMS-VISIT-10",
            add_project=True,
        )
        # Update container IDs to avoid conflicts
        session2.id = "session-124"
        acquisition2.id = "acq-457"
        acquisition2.parents.session = "session-124"
        csv_file2.parent_ref.id = "project-001"
        project2.id = "project-001"
        mock_proxy.add_container("session-124", session2)
        mock_proxy.add_container("acq-457", acquisition2)
        mock_proxy.add_container("project-001", project2)

        accumulator.record_file_queued(file=csv_file2, module="UDS", project=project2)
        temp_key_10 = VisitKey(ptid="temp_10", visit_date="", module="UDS")
        assert temp_key_10 in accumulator.pending

    def test_packet_optional(self, accumulator, mock_proxy, mock_event_logger):
        """Test that packet field is optional in metadata.

        Setup:
        - At queue time: CSV only
        - At completion: CSV + JSON without packet field

        Expected: Events logged with packet=None
        """
        session, acquisition, csv_file, project = self.setup_containers(
            mock_proxy, add_project=True
        )

        # Queue file with no metadata
        accumulator.record_file_queued(file=csv_file, module="UDS", project=project)

        # Add JSON file without packet
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

        # Log outcome
        accumulator.log_outcome_event(
            file=csv_file, module="UDS", pipeline_succeeded=True
        )

        # Events should be logged with packet=None
        assert len(mock_event_logger.logged_events) == 2
        submit_event = mock_event_logger.get_events_by_action("submit")[0]
        assert submit_event.packet is None
