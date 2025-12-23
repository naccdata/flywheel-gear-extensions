"""Integration tests for end-to-end event logging flow."""

from datetime import datetime
from typing import List, Optional

import pytest
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.event_accumulator import EventAccumulator
from nacc_common.error_models import (
    QC_STATUS_PASS,
    VisitMetadata,
)
from test_mocks.mock_event_logging import MockVisitEventLogger
from test_mocks.mock_factories import (
    FileEntryFactory,
    QCMetadataFactory,
    VisitMetadataFactory,
)
from test_mocks.mock_flywheel import (
    MockFile,
    MockProjectAdaptor,
    create_mock_file_with_parent,
)


class MockProjectAdaptorIntegration(MockProjectAdaptor):
    """Extended MockProject for integration testing."""

    def __init__(
        self,
        label: str,
        group: str = "dummy-center",
        pipeline_adcid: int = 42,
        files: Optional[List[FileEntry]] = None,
    ):
        super().__init__(label)
        self.__group = group
        self._pipeline_adcid = pipeline_adcid
        if files:
            for file in files:
                self._MockProjectAdaptor__files[file.name] = file  # type: ignore

    @property
    def group(self):
        return self.__group

    def get_pipeline_adcid(self) -> int:
        """Get pipeline ADCID."""
        return self._pipeline_adcid

    def iter_files(self, **kwargs):
        """Iterate over files with optional filtering."""
        file_filter = kwargs.get("filter")
        if file_filter:
            return filter(file_filter, self.files)
        return iter(self.files)


def create_mock_json_file_with_forms_metadata(
    name: str,
    ptid: str,
    visitdate: str,
    visitnum: str,
    module: str,
    packet: str,
    parent_id: str = "acquisition-123",
) -> MockFile:
    """Create a mock JSON file with forms metadata.

    Args:
        name: File name
        ptid: Participant ID
        visitdate: Visit date
        visitnum: Visit number
        module: Module name
        packet: Packet identifier
        parent_id: Parent acquisition ID

    Returns:
        MockFile with forms metadata
    """
    return FileEntryFactory.create_mock_json_file_with_forms_metadata(
        name=name,
        ptid=ptid,
        visitdate=visitdate,
        visitnum=visitnum,
        module=module,
        packet=packet,
        parent_id=parent_id,
    )


def create_mock_qc_status_file_with_visit_metadata(
    ptid: str,
    date: str,
    module: str,
    qc_metadata,
    visit_metadata: Optional[VisitMetadata] = None,
    modified: Optional[datetime] = None,
) -> MockFile:
    """Create a mock QC-status file with visit metadata in custom info.

    Args:
        ptid: Participant ID
        date: Visit date
        module: Module name (e.g., "uds")
        qc_metadata: FileQCModel instance
        visit_metadata: VisitMetadata to include in custom info
        modified: File modification timestamp

    Returns:
        MockFile with QC metadata and visit metadata in custom info
    """
    return FileEntryFactory.create_mock_qc_status_file_with_visit_metadata(
        ptid=ptid,
        date=date,
        module=module,
        qc_metadata=qc_metadata,
        visit_metadata=visit_metadata,
        modified=modified,
    )


class TestEndToEndEventLogging:
    """Integration tests for end-to-end event logging flow."""

    @pytest.fixture
    def mock_event_logger(self) -> MockVisitEventLogger:
        """Create mock event logger."""
        return MockVisitEventLogger()

    @pytest.fixture
    def event_accumulator(
        self, mock_event_logger: MockVisitEventLogger
    ) -> EventAccumulator:
        """Create EventAccumulator instance."""
        return EventAccumulator(event_logger=mock_event_logger)

    def test_end_to_end_qc_pass_event_with_visit_metadata_from_custom_info(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test end-to-end flow: JSON file -> QC status discovery ->
        VisitMetadata extraction from custom info -> QC-pass event creation ->
        S3 logging.

        This tests the complete flow when visit metadata is available in
        QC status custom info (added by FileVisitAnnotator).
        """
        # Create JSON file in finalization queue
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100000_FORMS-VISIT-3F_UDS.json",
            ptid="adrc1000",
            visitdate="2025-03-19",
            visitnum="3F",
            module="UDS",
            packet="I",
        )

        # Create visit metadata for QC status custom info
        visit_metadata = VisitMetadataFactory.create_visit_metadata(
            ptid="adrc1000",
            date="2025-03-19",
            visitnum="3F",
            module="UDS",
            packet="I",
        )

        # Create QC metadata with PASS status
        qc_metadata = QCMetadataFactory.create_qc_metadata_with_status(
            {
                "identifier-lookup": QC_STATUS_PASS,
                "form-transformer": QC_STATUS_PASS,
                "form-qc-coordinator": QC_STATUS_PASS,
                "form-qc-checker": QC_STATUS_PASS,
            }
        )

        # Create QC-status file with visit metadata in custom info
        qc_completion_time = datetime(2025, 3, 19, 11, 30, 0)
        qc_file = create_mock_qc_status_file_with_visit_metadata(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata,
            visit_metadata=visit_metadata,
            modified=qc_completion_time,
        )

        # Create mock project
        project = MockProjectAdaptorIntegration(
            label="ingest-form-alpha",
            group="dummy-center",
            pipeline_adcid=42,
            files=[qc_file],
        )

        # Execute end-to-end event logging
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify QC-pass event was created and logged
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        # Verify event structure and content
        assert event.action == "pass-qc"
        assert event.gear_name == "form-scheduler"
        assert event.ptid == "adrc1000"
        assert event.visit_date == "2025-03-19"
        assert event.visit_number == "3F"
        assert event.module == "UDS"
        assert event.packet == "I"
        assert event.study == "alpha"  # Extracted from project label
        assert event.project_label == "ingest-form-alpha"
        assert event.center_label == "dummy-center"
        assert event.pipeline_adcid == 42
        assert event.datatype == "form"
        assert event.timestamp == qc_completion_time

    def test_end_to_end_qc_pass_event_with_visit_metadata_from_json_fallback(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test end-to-end flow with fallback to JSON file metadata when QC
        status custom info is not available.

        This tests the fallback mechanism when FileVisitAnnotator hasn't
        added visit metadata to the QC status file.
        """
        # Create JSON file in finalization queue
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100001_FORMS-VISIT-4F_FTLD.json",
            ptid="adrc1001",
            visitdate="2025-08-22",
            visitnum="4F",
            module="FTLD",
            packet="F",
        )

        # Create QC metadata with PASS status (no visit metadata in custom info)
        qc_metadata = QCMetadataFactory.create_qc_metadata_with_status(
            {
                "identifier-lookup": QC_STATUS_PASS,
                "form-transformer": QC_STATUS_PASS,
                "form-qc-coordinator": QC_STATUS_PASS,
                "form-qc-checker": QC_STATUS_PASS,
            }
        )

        # Create QC-status file WITHOUT visit metadata in custom info
        qc_completion_time = datetime(2025, 8, 22, 14, 45, 0)
        qc_file = create_mock_qc_status_file_with_visit_metadata(
            ptid="adrc1001",
            date="2025-08-22",
            module="ftld",
            qc_metadata=qc_metadata,
            visit_metadata=None,  # No visit metadata in custom info
            modified=qc_completion_time,
        )

        # Create mock project
        project = MockProjectAdaptorIntegration(
            label="ingest-form-beta",
            group="test-center",
            pipeline_adcid=123,
            files=[qc_file],
        )

        # Execute end-to-end event logging
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify QC-pass event was created using JSON file metadata
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        # Verify event structure and content from JSON fallback
        assert event.action == "pass-qc"
        assert event.gear_name == "form-scheduler"
        assert event.ptid == "adrc1001"
        assert event.visit_date == "2025-08-22"  # From JSON visitdate
        assert event.visit_number == "4F"
        assert event.module == "FTLD"
        assert event.packet == "F"
        assert event.study == "beta"
        assert event.project_label == "ingest-form-beta"
        assert event.center_label == "test-center"
        assert event.pipeline_adcid == 123
        assert event.timestamp == qc_completion_time

    def test_end_to_end_qc_status_log_discovery_using_error_log_template(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test QC status log discovery using ErrorLogTemplate to generate
        expected filename from JSON file metadata.

        This verifies that the EventAccumulator correctly uses
        ErrorLogTemplate to find the corresponding QC status log for a
        JSON file.
        """
        # Create JSON file with specific metadata for template matching
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC274180_FORMS-VISIT-2F_UDS.json",
            ptid="adrc1002",
            visitdate="2025-06-18",
            visitnum="2F",
            module="UDS",
            packet="I",
        )

        # Create visit metadata
        visit_metadata = VisitMetadataFactory.create_visit_metadata(
            ptid="adrc1002",
            date="2025-06-18",
            visitnum="2F",
            module="UDS",
            packet="I",
        )

        # Create QC metadata with PASS status
        qc_metadata = QCMetadataFactory.create_qc_metadata_with_status(
            {
                "form-qc-coordinator": QC_STATUS_PASS,
                "form-qc-checker": QC_STATUS_PASS,
            }
        )

        # Create QC-status file with filename that matches ErrorLogTemplate pattern
        # ErrorLogTemplate should generate: "adrc1002_2025-06-18_uds_qc-status.log"
        qc_completion_time = datetime(2025, 6, 18, 16, 20, 0)
        qc_file = create_mock_qc_status_file_with_visit_metadata(
            ptid="adrc1002",
            date="2025-06-18",
            module="uds",  # lowercase for filename
            qc_metadata=qc_metadata,
            visit_metadata=visit_metadata,
            modified=qc_completion_time,
        )

        # Create mock project with the QC status file
        project = MockProjectAdaptorIntegration(
            label="ingest-form-gamma",
            files=[qc_file],
        )

        # Execute event logging - should find QC file using ErrorLogTemplate
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify event was logged (confirms QC status log was found)
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "pass-qc"
        assert event.ptid == "adrc1002"
        assert event.visit_date == "2025-06-18"
        assert event.module == "UDS"
        assert event.study == "gamma"

    def test_end_to_end_no_event_when_qc_status_not_pass(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that no events are logged when QC status is not PASS.

        This verifies that the EventAccumulator only logs events for
        visits that pass QC validation.
        """
        # Create JSON file
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100003_FORMS-VISIT-1F_UDS.json",
            ptid="adrc1003",
            visitdate="2025-10-15",
            visitnum="1F",
            module="UDS",
            packet="I",
        )

        # Create QC metadata with FAIL status
        qc_metadata = QCMetadataFactory.create_fail_qc_metadata(
            failing_gear="form-qc-checker",
            gear_names=[
                "identifier-lookup",
                "form-transformer",
                "form-qc-coordinator",
                "form-qc-checker",
            ],
        )

        # Create QC-status file
        qc_file = create_mock_qc_status_file_with_visit_metadata(
            ptid="adrc1003",
            date="2025-10-15",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 10, 15, 13, 0, 0),
        )

        # Create mock project
        project = MockProjectAdaptorIntegration(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Execute event logging
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify no events were logged (QC status is not PASS)
        assert len(mock_event_logger.logged_events) == 0

    def test_end_to_end_no_event_when_qc_status_log_not_found(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that no events are logged when QC status log is not found.

        This verifies graceful handling when the corresponding QC status
        log doesn't exist for a JSON file.
        """
        # Create JSON file
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100004_FORMS-VISIT-5F_UDS.json",
            ptid="adrc1004",
            visitdate="2025-12-01",
            visitnum="5F",
            module="UDS",
            packet="I",
        )

        # Create mock project with NO QC status files
        project = MockProjectAdaptorIntegration(
            label="ingest-form-alpha",
            files=[],  # No QC status files
        )

        # Execute event logging
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify no events were logged (no QC status log found)
        assert len(mock_event_logger.logged_events) == 0

    def test_end_to_end_no_event_when_visit_metadata_invalid(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that no events are logged when visit metadata is invalid.

        This verifies that the EventAccumulator skips event logging when
        visit metadata is incomplete or invalid.
        """
        # Create JSON file with incomplete forms metadata (missing required fields)
        incomplete_forms_metadata = {
            "forms": {
                "json": {
                    "ptid": "adrc1005",
                    # Missing visitdate, visitnum, module - required for VisitEvent
                    "packet": "I",
                }
            }
        }

        json_file = create_mock_file_with_parent(
            name="NACC100005_FORMS-VISIT-6F_UDS.json",
            parent_id="acquisition-456",
            info=incomplete_forms_metadata,
        )

        # Create QC metadata with PASS status
        qc_metadata = QCMetadataFactory.create_pass_qc_metadata(["form-qc-checker"])

        # Create QC-status file (also without visit metadata in custom info)
        qc_file = create_mock_qc_status_file_with_visit_metadata(
            ptid="adrc1005",
            date="2025-11-20",
            module="uds",
            qc_metadata=qc_metadata,
            visit_metadata=None,  # No visit metadata in custom info
            modified=datetime(2025, 11, 20, 10, 0, 0),
        )

        # Create mock project
        project = MockProjectAdaptorIntegration(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Execute event logging
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify no events were logged (invalid visit metadata)
        assert len(mock_event_logger.logged_events) == 0

    def test_end_to_end_error_resilience_continues_processing(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that event logging errors don't stop processing.

        This verifies that the EventAccumulator handles errors
        gracefully and continues processing without failing.
        """
        # Create JSON file
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100006_FORMS-VISIT-7F_UDS.json",
            ptid="adrc1006",
            visitdate="2025-09-30",
            visitnum="7F",
            module="UDS",
            packet="I",
        )

        # Create mock project with invalid label format (will cause ValidationError)
        project = MockProjectAdaptorIntegration(
            label="invalid-label-format",  # Doesn't match PipelineLabel pattern
            files=[],
        )

        # Execute event logging - should handle error gracefully
        # This should not raise an exception
        event_accumulator.log_events(json_file=json_file, project=project)

        # Verify no events were logged due to error, but no exception was raised
        assert len(mock_event_logger.logged_events) == 0

    def test_end_to_end_missing_event_logger_configuration(self) -> None:
        """Test that event logging is skipped when event logger is None.

        This verifies that the system handles missing event logger
        configuration gracefully without errors.
        """
        # Create EventAccumulator with None event logger
        event_accumulator = EventAccumulator(
            event_logger=None,  # type: ignore
        )

        # Create JSON file
        json_file = create_mock_json_file_with_forms_metadata(
            name="NACC100007_FORMS-VISIT-8F_UDS.json",
            ptid="adrc1007",
            visitdate="2025-07-14",
            visitnum="8F",
            module="UDS",
            packet="I",
        )

        # Create mock project
        project = MockProjectAdaptorIntegration(
            label="ingest-form-alpha",
            files=[],
        )

        # Execute event logging - should handle None logger gracefully
        # This should not raise an exception
        event_accumulator.log_events(json_file=json_file, project=project)

        # No assertions needed - the test passes if no exception is raised
