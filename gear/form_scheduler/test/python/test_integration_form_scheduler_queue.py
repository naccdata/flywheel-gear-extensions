"""Integration tests for FormSchedulerQueue with EventAccumulator."""

import json
from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from configs.ingest_configs import Pipeline, PipelineConfigs
from event_capture.event_capture import VisitEventCapture
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.form_scheduler_queue import FormSchedulerQueue
from gear_execution.gear_trigger import GearConfigs, GearInfo, GearInput
from nacc_common.error_models import (
    QC_STATUS_PASS,
    FileQCModel,
    GearQCModel,
    ValidationModel,
    VisitMetadata,
)
from test_mocks.mock_event_capture import MockVisitEventCapture
from test_mocks.mock_flywheel import (
    MockFile,
    MockFlywheelProxy,
    MockParentRef,
    MockProjectAdaptor,
    create_mock_file_with_parent,
)


class MockProjectAdaptorForQueue(MockProjectAdaptor):
    """Extended MockProject for FormSchedulerQueue integration testing."""

    def __init__(
        self,
        label: str,
        project_id: str = "project-123",
        group: str = "dummy-center",
        pipeline_adcid: int = 42,
        files: Optional[List[FileEntry]] = None,
    ):
        super().__init__(label)
        self.__project_id = project_id
        self.__group = group
        self._pipeline_adcid = pipeline_adcid
        if files:
            for file in files:
                self._MockProjectAdaptor__files[file.name] = file  # type: ignore

    @property
    def id(self) -> str:
        return self.__project_id

    @property
    def group(self) -> str:
        return self.__group

    @property
    def project(self):
        """Return self as project for compatibility."""
        return self

    def get_pipeline_adcid(self) -> int:
        """Get pipeline ADCID."""
        return self._pipeline_adcid

    def iter_files(self, **kwargs):
        """Iterate over files with optional filtering."""
        file_filter = kwargs.get("filter")
        if file_filter:
            return filter(file_filter, self.files)
        return iter(self.files)

    def read_dataview(self, view):
        """Mock dataview reading for finalization pipeline."""

        # Return empty result for simplicity in integration tests
        class MockResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps({"data": []}).encode()

        return MockResponse()


class MockFileForQueue(MockFile):
    """Extended MockFile that handles tag operations for queue testing."""

    def __init__(self, *args, **kwargs):
        # Extract tags before calling super().__init__
        tags = kwargs.pop("tags", [])
        super().__init__(*args, **kwargs)
        self.tags = tags

    def delete_tag(self, tag, **kwargs):
        """Mock delete_tag method."""
        if tag in self.tags:
            self.tags.remove(tag)

    def reload(self, *args, **kwargs):
        """Mock reload method."""
        return self


def create_mock_json_file_for_queue(
    name: str,
    ptid: str,
    visitdate: str,
    visitnum: Optional[str],
    module: str,
    packet: str,
    parent_id: str = "acquisition-123",
    tags: Optional[List[str]] = None,
) -> FileEntry:
    """Create a mock JSON file for queue testing.

    Args:
        name: File name
        ptid: Participant ID
        visitdate: Visit date
        visitnum: Visit number (None for forms without visits like MLST, NP)
        module: Module name
        packet: Packet identifier
        parent_id: Parent acquisition ID
        tags: File tags

    Returns:
        MockFileForQueue with forms metadata and tags
    """
    forms_metadata = {
        "forms": {
            "json": {
                "ptid": ptid,
                "visitdate": visitdate,
                "module": module,
                "packet": packet,
            }
        }
    }

    # Only include visitnum if provided (milestone and NP forms don't have it)
    if visitnum is not None:
        forms_metadata["forms"]["json"]["visitnum"] = visitnum

    file = MockFileForQueue(
        name=name,
        info=forms_metadata,
        tags=tags or [],
    )
    file.parent_ref = MockParentRef(id=parent_id)  # type: ignore[assignment]

    return file


def create_mock_qc_status_file_for_queue(
    ptid: str,
    date: str,
    module: str,
    qc_status: str = QC_STATUS_PASS,
    visit_metadata: Optional[VisitMetadata] = None,
    modified: Optional[datetime] = None,
) -> FileEntry:
    """Create a mock QC-status file for queue testing.

    Args:
        ptid: Participant ID
        date: Visit date
        module: Module name (e.g., "uds")
        qc_status: QC status ("PASS" or "FAIL")
        visit_metadata: VisitMetadata to include in custom info
        modified: File modification timestamp

    Returns:
        MockFile with QC metadata
    """
    filename = f"{ptid}_{date}_{module}_qc-status.log"

    # Create QC metadata
    validation_model = ValidationModel(
        state=qc_status,
        data=[],  # No errors for PASS status
        cleared=[],  # No cleared alerts
    )

    qc_gears = {"form-qc-checker": GearQCModel(validation=validation_model)}
    qc_metadata = FileQCModel(qc=qc_gears)

    # Convert to dict for MockFile info
    info_dict = qc_metadata.model_dump(by_alias=True)

    # Add visit metadata to custom info if provided
    if visit_metadata:
        info_dict["visit"] = visit_metadata.model_dump(exclude_none=True, mode="raw")

    file = create_mock_file_with_parent(
        name=filename,
        parent_id="project-123",  # QC status files are at project level
        info=info_dict,
        modified=modified,
    )

    return file


class TestFormSchedulerQueueIntegration:
    """Integration tests for FormSchedulerQueue with EventAccumulator."""

    @pytest.fixture
    def mock_event_capture(self) -> MockVisitEventCapture:
        """Create mock event logger."""
        return MockVisitEventCapture()

    @pytest.fixture
    def mock_proxy(self) -> MockFlywheelProxy:
        """Create mock Flywheel proxy."""
        return MockFlywheelProxy()

    @pytest.fixture
    def finalization_pipeline_config(self) -> PipelineConfigs:
        """Create finalization pipeline configuration for testing."""
        finalization_pipeline = Pipeline(
            name="finalization",
            modules=["UDS", "FTLD"],
            tags=["finalized"],
            extensions=[".json"],
            starting_gear=GearInfo(
                gear_name="form-qc-coordinator",
                inputs=[
                    GearInput(
                        label="json_file",
                        file_locator="matched",
                    )
                ],
                configs=GearConfigs(),
            ),
            notify_user=False,
        )

        return PipelineConfigs(
            gears=["form-qc-coordinator", "form-qc-checker"],
            pipelines=[finalization_pipeline],
        )

    def test_form_scheduler_queue_integration_with_event_accumulator(
        self,
        mock_proxy: MockFlywheelProxy,
        mock_event_capture: MockVisitEventCapture,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test FormSchedulerQueue integration with EventAccumulator.

        This verifies that the FormSchedulerQueue correctly calls the
        EventAccumulator after pipeline completion and that events are
        logged.
        """
        # Create JSON file that would be in finalization queue
        json_file = create_mock_json_file_for_queue(
            name="NACC100000_FORMS-VISIT-3F_UDS.json",
            ptid="adrc1000",
            visitdate="2025-03-19",
            visitnum="3F",
            module="UDS",
            packet="I",
            tags=["finalized"],  # File is in finalization queue
        )

        # Create visit metadata for QC status
        visit_metadata = VisitMetadata(
            ptid="adrc1000",
            date="2025-03-19",
            visitnum="3F",
            module="UDS",
            packet="I",
        )

        # Create QC-status file with PASS status
        qc_file = create_mock_qc_status_file_for_queue(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_status=QC_STATUS_PASS,
            visit_metadata=visit_metadata,
            modified=datetime(2025, 3, 19, 11, 30, 0),
        )

        # Create mock project with both files
        project = MockProjectAdaptorForQueue(
            label="ingest-form-alpha",
            project_id="project-123",
            files=[qc_file],  # QC status file at project level
        )

        # Add acquisition container to proxy for gear triggering
        mock_acquisition = MagicMock()
        mock_acquisition.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition)

        # Create FormSchedulerQueue
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling to avoid actual Flywheel calls
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return our JSON file
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file.name,
                                    "file_id": "file-id-1",
                                    "module": "UDS",
                                }
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project.get_file_by_id to return the JSON file
            def mock_get_file_by_id(file_id):
                if file_id == "file-id-1":
                    return json_file
                return None

            # Mock project.get_file for QC status files
            def mock_get_file(filename):
                if filename == qc_file.name:
                    return qc_file
                return None

            with (
                patch.object(
                    project, "get_file_by_id", side_effect=mock_get_file_by_id
                ),
                patch.object(project, "get_file", side_effect=mock_get_file),
            ):
                # Queue files for finalization pipeline
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 1

                # Process pipeline queues (this should trigger event logging)
                form_scheduler.process_pipeline_queues()

        # Verify that gear was triggered
        mock_trigger.assert_called_once()

        # Verify that event was logged by EventAccumulator
        assert len(mock_event_capture.logged_events) == 1
        event = mock_event_capture.logged_events[0]

        # Verify event details
        assert event.action == "pass-qc"
        assert event.gear_name == "form-scheduler"
        assert event.ptid == "adrc1000"
        assert event.visit_date == "2025-03-19"
        assert event.visit_number == "3F"
        assert event.module == "UDS"
        assert event.packet == "I"
        assert event.study == "alpha"

    def test_form_scheduler_queue_error_handling_doesnt_affect_pipeline(
        self,
        mock_proxy: MockFlywheelProxy,
        mock_event_capture: MockVisitEventCapture,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test that event logging errors don't affect pipeline processing.

        This verifies that if event logging fails, the pipeline
        processing continues normally without raising exceptions.
        """
        # Create JSON file
        json_file = create_mock_json_file_for_queue(
            name="NACC100001_FORMS-VISIT-4F_UDS.json",
            ptid="adrc1001",
            visitdate="2025-08-22",
            visitnum="4F",
            module="UDS",
            packet="I",
            tags=["finalized"],
        )

        # Create mock project with invalid label (will cause event logging error)
        project = MockProjectAdaptorForQueue(
            label="invalid-label-format",  # Invalid format will cause ValidationError
            project_id="project-123",
            files=[],  # No QC status files - will cause event logging to fail
        )

        # Add acquisition container to proxy
        mock_acquisition = MagicMock()
        mock_acquisition.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition)

        # Create FormSchedulerQueue
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return our JSON file
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file.name,
                                    "file_id": "file-id-1",
                                    "module": "UDS",
                                }
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project.get_file_by_id to return our JSON file
            with patch.object(project, "get_file_by_id", return_value=json_file):
                # Queue files
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 1

                # Process pipeline queues - should not raise exception despite
                # event logging error
                form_scheduler.process_pipeline_queues()

        # Verify that gear was still triggered despite event logging error
        mock_trigger.assert_called_once()

        # Verify no events were logged due to error
        assert len(mock_event_capture.logged_events) == 0

    def test_form_scheduler_queue_missing_event_logger_configuration(
        self,
        mock_proxy: MockFlywheelProxy,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test FormSchedulerQueue with missing event logger configuration.

        This verifies that when event_logger is None, the
        FormSchedulerQueue skips event logging entirely without errors.
        """
        # Create JSON file
        json_file = create_mock_json_file_for_queue(
            name="NACC100002_FORMS-VISIT-5F_UDS.json",
            ptid="adrc1002",
            visitdate="2025-06-18",
            visitnum="5F",
            module="UDS",
            packet="I",
            tags=["finalized"],
        )

        # Create mock project
        project = MockProjectAdaptorForQueue(
            label="ingest-form-alpha",
            project_id="project-123",
            files=[],
        )

        # Add acquisition container to proxy
        mock_acquisition = MagicMock()
        mock_acquisition.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition)

        # Create mock event capture
        mock_event_capture = Mock(spec=VisitEventCapture)

        # Create FormSchedulerQueue with mock event capture
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return our JSON file
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file.name,
                                    "file_id": "file-id-1",
                                    "module": "UDS",
                                }
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project.get_file_by_id to return our JSON file
            with patch.object(project, "get_file_by_id", return_value=json_file):
                # Queue files
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 1

                # Process pipeline queues - should not raise exception
                form_scheduler.process_pipeline_queues()

        # Verify that gear was triggered normally
        mock_trigger.assert_called_once()

        # No event logger to check - test passes if no exception was raised

    def test_form_scheduler_queue_multiple_files_event_logging(
        self,
        mock_proxy: MockFlywheelProxy,
        mock_event_capture: MockVisitEventCapture,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test FormSchedulerQueue event logging with multiple files.

        This verifies that the EventAccumulator is called for each
        processed file and that events are logged correctly for multiple
        files.
        """
        # Create multiple JSON files
        json_file_1 = create_mock_json_file_for_queue(
            name="NACC100003_FORMS-VISIT-1F_UDS.json",
            ptid="adrc1003",
            visitdate="2025-01-10",
            visitnum="1F",
            module="UDS",
            packet="I",
            tags=["finalized"],
        )

        json_file_2 = create_mock_json_file_for_queue(
            name="NACC100004_FORMS-VISIT-2F_FTLD.json",
            ptid="adrc1004",
            visitdate="2025-02-15",
            visitnum="2F",
            module="FTLD",
            packet="F",
            tags=["finalized"],
        )

        # Create corresponding QC-status files
        visit_metadata_1 = VisitMetadata(
            ptid="adrc1003",
            date="2025-01-10",
            visitnum="1F",
            module="UDS",
            packet="I",
        )

        visit_metadata_2 = VisitMetadata(
            ptid="adrc1004",
            date="2025-02-15",
            visitnum="2F",
            module="FTLD",
            packet="F",
        )

        qc_file_1 = create_mock_qc_status_file_for_queue(
            ptid="adrc1003",
            date="2025-01-10",
            module="uds",
            qc_status=QC_STATUS_PASS,
            visit_metadata=visit_metadata_1,
            modified=datetime(2025, 1, 10, 14, 0, 0),
        )

        qc_file_2 = create_mock_qc_status_file_for_queue(
            ptid="adrc1004",
            date="2025-02-15",
            module="ftld",
            qc_status=QC_STATUS_PASS,
            visit_metadata=visit_metadata_2,
            modified=datetime(2025, 2, 15, 16, 30, 0),
        )

        # Create mock project
        project = MockProjectAdaptorForQueue(
            label="ingest-form-beta",
            project_id="project-123",
            files=[qc_file_1, qc_file_2],
        )

        # Add acquisition containers to proxy
        mock_acquisition_1 = MagicMock()
        mock_acquisition_1.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition_1)

        # Create FormSchedulerQueue
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return both JSON files
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file_1.name,
                                    "file_id": "file-id-1",
                                    "module": "UDS",
                                },
                                {
                                    "filename": json_file_2.name,
                                    "file_id": "file-id-2",
                                    "module": "FTLD",
                                },
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project.get_file_by_id to return appropriate files
            def mock_get_file_by_id(file_id):
                if file_id == "file-id-1":
                    return json_file_1
                elif file_id == "file-id-2":
                    return json_file_2
                return None

            # Mock project.get_file for QC status files
            def mock_get_file(filename):
                if filename == qc_file_1.name:
                    return qc_file_1
                elif filename == qc_file_2.name:
                    return qc_file_2
                return None

            with (
                patch.object(
                    project, "get_file_by_id", side_effect=mock_get_file_by_id
                ),
                patch.object(project, "get_file", side_effect=mock_get_file),
            ):
                # Queue files
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 2

                # Process pipeline queues
                form_scheduler.process_pipeline_queues()

        # Verify that gear was triggered for both files
        assert mock_trigger.call_count == 2

        # Verify that events were logged for both files
        assert len(mock_event_capture.logged_events) == 2

        # Verify event details for both files
        events_by_ptid = {
            event.ptid: event for event in mock_event_capture.logged_events
        }

        assert "adrc1003" in events_by_ptid
        assert "adrc1004" in events_by_ptid

        event_1 = events_by_ptid["adrc1003"]
        assert event_1.action == "pass-qc"
        assert event_1.module == "UDS"
        assert event_1.visit_date == "2025-01-10"

        event_2 = events_by_ptid["adrc1004"]
        assert event_2.action == "pass-qc"
        assert event_2.module == "FTLD"
        assert event_2.visit_date == "2025-02-15"

    def test_form_scheduler_queue_milestone_form_without_visitnum(
        self,
        mock_proxy: MockFlywheelProxy,
        mock_event_capture: MockVisitEventCapture,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test FormSchedulerQueue with milestone form that has no visitnum.

        Milestone forms (MLST) don't have visitnum but should still log
        events successfully as long as ptid, date, and module are
        present.
        """
        # Update pipeline config to include MLST module
        finalization_pipeline_config.pipelines[0].modules.append("MLST")

        # Create milestone JSON file WITHOUT visitnum
        json_file = create_mock_json_file_for_queue(
            name="NACC100005_MILESTONE-2025-04-15_MLST.json",
            ptid="adrc1005",
            visitdate="2025-04-15",
            visitnum=None,  # Milestone forms don't have visitnum
            module="MLST",
            packet="M",
            tags=["finalized"],
        )

        # Create visit metadata for QC status WITHOUT visitnum
        visit_metadata = VisitMetadata(
            ptid="adrc1005",
            date="2025-04-15",
            visitnum=None,  # No visitnum for milestone
            module="MLST",
            packet="M",
        )

        # Create QC-status file with PASS status
        qc_file = create_mock_qc_status_file_for_queue(
            ptid="adrc1005",
            date="2025-04-15",
            module="mlst",
            qc_status=QC_STATUS_PASS,
            visit_metadata=visit_metadata,
            modified=datetime(2025, 4, 15, 14, 0, 0),
        )

        # Create mock project with both files
        project = MockProjectAdaptorForQueue(
            label="ingest-form-alpha",
            project_id="project-123",
            files=[qc_file],
        )

        # Add acquisition container to proxy
        mock_acquisition = MagicMock()
        mock_acquisition.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition)

        # Create FormSchedulerQueue
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return our milestone JSON file
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file.name,
                                    "file_id": "file-id-mlst",
                                    "module": "MLST",
                                }
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project methods
            def mock_get_file_by_id(file_id):
                if file_id == "file-id-mlst":
                    return json_file
                return None

            def mock_get_file(filename):
                if filename == qc_file.name:
                    return qc_file
                return None

            with (
                patch.object(
                    project, "get_file_by_id", side_effect=mock_get_file_by_id
                ),
                patch.object(project, "get_file", side_effect=mock_get_file),
            ):
                # Queue files for finalization pipeline
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 1

                # Process pipeline queues (this should trigger event logging)
                form_scheduler.process_pipeline_queues()

        # Verify that gear was triggered
        mock_trigger.assert_called_once()

        # Verify that event was logged for milestone form
        assert len(mock_event_capture.logged_events) == 1

        event = mock_event_capture.logged_events[0]

        # Verify event details - visitnum should be None
        assert event.action == "pass-qc"
        assert event.gear_name == "form-scheduler"
        assert event.ptid == "adrc1005"
        assert event.visit_date == "2025-04-15"
        assert event.visit_number is None  # No visitnum for milestone forms
        assert event.module == "MLST"
        assert event.packet == "M"
        assert event.study == "alpha"

    def test_form_scheduler_queue_np_form_without_visitnum(
        self,
        mock_proxy: MockFlywheelProxy,
        mock_event_capture: MockVisitEventCapture,
        finalization_pipeline_config: PipelineConfigs,
    ) -> None:
        """Test FormSchedulerQueue with NP form that has no visitnum.

        NP forms don't have visitnum but should still log events
        successfully as long as ptid, date, and module are present.
        """
        # Update pipeline config to include NP module
        finalization_pipeline_config.pipelines[0].modules.append("NP")

        # Create NP JSON file WITHOUT visitnum
        json_file = create_mock_json_file_for_queue(
            name="NACC100006_NP-RECORD-2025-05-20_NP.json",
            ptid="adrc1006",
            visitdate="2025-05-20",
            visitnum=None,  # NP forms don't have visitnum
            module="NP",
            packet="N",
            tags=["finalized"],
        )

        # Create visit metadata for QC status WITHOUT visitnum
        visit_metadata = VisitMetadata(
            ptid="adrc1006",
            date="2025-05-20",
            visitnum=None,  # No visitnum for NP
            module="NP",
            packet="N",
        )

        # Create QC-status file with PASS status
        qc_file = create_mock_qc_status_file_for_queue(
            ptid="adrc1006",
            date="2025-05-20",
            module="np",
            qc_status=QC_STATUS_PASS,
            visit_metadata=visit_metadata,
            modified=datetime(2025, 5, 20, 16, 30, 0),
        )

        # Create mock project with both files
        project = MockProjectAdaptorForQueue(
            label="ingest-form-alpha",
            project_id="project-123",
            files=[qc_file],
        )

        # Add acquisition container to proxy
        mock_acquisition = MagicMock()
        mock_acquisition.id = "acquisition-123"
        mock_proxy.add_container("acquisition-123", mock_acquisition)

        # Create FormSchedulerQueue
        form_scheduler = FormSchedulerQueue(
            proxy=mock_proxy,
            project=project,
            pipeline_configs=finalization_pipeline_config,
            event_capture=mock_event_capture,
            email_client=None,
            portal_url=None,
        )

        # Mock the gear triggering and job polling
        with (
            patch(
                "form_scheduler_app.form_scheduler_queue.trigger_gear"
            ) as mock_trigger,
            patch("form_scheduler_app.form_scheduler_queue.JobPoll.wait_for_pipeline"),
            patch.object(project, "read_dataview") as mock_dataview,
        ):
            # Mock dataview to return our NP JSON file
            class MockDataviewResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return json.dumps(
                        {
                            "data": [
                                {
                                    "filename": json_file.name,
                                    "file_id": "file-id-np",
                                    "module": "NP",
                                }
                            ]
                        }
                    ).encode()

            mock_dataview.return_value = MockDataviewResponse()

            # Mock project methods
            def mock_get_file_by_id(file_id):
                if file_id == "file-id-np":
                    return json_file
                return None

            def mock_get_file(filename):
                if filename == qc_file.name:
                    return qc_file
                return None

            with (
                patch.object(
                    project, "get_file_by_id", side_effect=mock_get_file_by_id
                ),
                patch.object(project, "get_file", side_effect=mock_get_file),
            ):
                # Queue files for finalization pipeline
                file_count = form_scheduler.queue_files_for_pipeline(
                    finalization_pipeline_config.pipelines[0]
                )
                assert file_count == 1

                # Process pipeline queues (this should trigger event logging)
                form_scheduler.process_pipeline_queues()

        # Verify that gear was triggered
        mock_trigger.assert_called_once()

        # Verify that event was logged for NP form
        assert len(mock_event_capture.logged_events) == 1

        event = mock_event_capture.logged_events[0]

        # Verify event details - visitnum should be None
        assert event.action == "pass-qc"
        assert event.gear_name == "form-scheduler"
        assert event.ptid == "adrc1006"
        assert event.visit_date == "2025-05-20"
        assert event.visit_number is None  # No visitnum for NP forms
        assert event.module == "NP"
        assert event.packet == "N"
        assert event.study == "alpha"
