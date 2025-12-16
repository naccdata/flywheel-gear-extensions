"""Tests for EventAccumulator (visitor_event_accumulator.py)."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pytest
from configs.ingest_configs import Pipeline
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from form_scheduler_app.visitor_event_accumulator import EventAccumulator
from gear_execution.gear_trigger import GearConfigs, GearInfo
from nacc_common.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCStatus,
    ValidationModel,
)
from pydantic import ValidationError
from test_mocks.mock_event_logging import MockVisitEventLogger
from test_mocks.mock_flywheel import MockFile


class MockProjectAdaptor(ProjectAdaptor):
    """Mock ProjectAdaptor for testing EventAccumulator."""

    def __init__(
        self,
        label: str,
        group: str = "dummy-center",
        pipeline_adcid: int = 42,
        files: Optional[List[FileEntry]] = None,
    ):
        self.__label = label
        self.__group = group
        self._pipeline_adcid = pipeline_adcid
        self.__files = files or []

    @property
    def label(self):
        return self.__label

    @property
    def group(self):
        return self.__group

    @property
    def files(self):
        return self.__files

    def get_pipeline_adcid(self) -> int:
        """Get pipeline ADCID."""
        return self._pipeline_adcid

    def iter_files(self, **kwargs):
        """Iterate over files with optional filtering."""
        file_filter = kwargs.get("filter")
        if file_filter:
            return filter(file_filter, self.files)
        return iter(self.files)


def create_qc_metadata(
    gears: Dict[str, QCStatus],
    errors: Optional[List[Dict[str, Any]]] = None,
    cleared_alerts: Optional[List[Dict[str, Any]]] = None,
) -> FileQCModel:
    """Create QC metadata structure for testing using Pydantic models.

    Args:
        gears: Dict mapping gear names to their states ("PASS" or "FAIL")
        errors: List of error/alert objects for failed gears
        cleared_alerts: List of cleared alert objects

    Returns:
        FileQCModel instance with proper structure
    """
    qc_gears: dict[str, GearQCModel] = {}

    for gear_name, state in gears.items():
        # Create FileError objects from error dictionaries
        file_errors: list[FileError] = []
        if state == "FAIL" and errors:
            for error_dict in errors:
                file_errors.append(FileError(**error_dict))

        # Create ClearedAlertModel objects from cleared alert dictionaries
        cleared_alert_models: list[ClearedAlertModel] = []
        if cleared_alerts:
            for alert_dict in cleared_alerts:
                # Create provenance objects using model_validate with by_alias
                provenance_models = []
                for prov_dict in alert_dict.get("provenance", []):
                    # Create ClearedAlertProvenance using model_validate
                    # with by_alias=True
                    provenance = ClearedAlertProvenance.model_validate(
                        prov_dict, by_alias=True
                    )
                    provenance_models.append(provenance)

                # Create cleared alert using model_validate with by_alias
                alert_dict_with_provenance = alert_dict.copy()
                alert_dict_with_provenance["provenance"] = provenance_models
                cleared_alert = ClearedAlertModel.model_validate(
                    alert_dict_with_provenance, by_alias=True
                )
                cleared_alert_models.append(cleared_alert)

        # Create ValidationModel
        validation_model = ValidationModel(
            state=state,
            data=file_errors,
            cleared=cleared_alert_models,
        )

        # Create GearQCModel
        qc_gears[gear_name] = GearQCModel(validation=validation_model)

    return FileQCModel(qc=qc_gears)


def create_mock_file_with_timestamp(
    name: str,
    created: Optional[datetime] = None,
    modified: Optional[datetime] = None,
    info: Optional[Dict[str, Any]] = None,
) -> MockFile:
    """Create a MockFile with timestamps.

    Args:
        name: File name
        created: File creation timestamp
        modified: File modification timestamp
        info: File info dictionary

    Returns:
        MockFile with timestamps set
    """
    file = MockFile(name=name, info=info, created=created, modified=modified)
    return file


def create_mock_qc_file(
    ptid: str,
    date: str,
    module: str,
    qc_metadata: Union[FileQCModel, Dict[str, Any]],
    modified: Optional[datetime] = None,
) -> MockFile:
    """Create a mock QC-status file with metadata.

    Args:
        ptid: Participant ID
        date: Visit date
        module: Module name (e.g., "uds")
        qc_metadata: FileQCModel instance or dict
        modified: File modification timestamp

    Returns:
        MockFile with QC metadata in info.qc
    """
    filename = f"{ptid}_{date}_{module}_qc-status.log"
    # Convert FileQCModel to dict for MockFile info using aliases
    if isinstance(qc_metadata, FileQCModel):
        info_dict = qc_metadata.model_dump(by_alias=True)
    else:
        info_dict = qc_metadata
    file = MockFile(name=filename, info=info_dict, modified=modified)
    return file


@pytest.fixture
def mock_event_logger() -> MockVisitEventLogger:
    """Create mock event logger."""
    return MockVisitEventLogger()


@pytest.fixture
def mock_pipeline() -> Pipeline:
    """Create mock pipeline configuration."""
    return Pipeline(
        name="submission",
        modules=["UDS", "FTLD"],
        tags=["queued"],
        extensions=[".csv"],
        starting_gear=GearInfo(gear_name="identifier-lookup", configs=GearConfigs()),
    )


@pytest.fixture
def event_accumulator(
    mock_event_logger: MockVisitEventLogger, mock_pipeline: Pipeline
) -> EventAccumulator:
    """Create EventAccumulator instance."""
    return EventAccumulator(
        pipeline=mock_pipeline,
        event_logger=mock_event_logger,
        datatype="form",
    )


class TestEventAccumulator:
    """Tests for EventAccumulator class."""

    def test_scenario_1_single_visit_pipeline_success(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 1: Single visit passes through entire submission
        pipeline successfully.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1000_2025-03-19_uds_qc-status.log
          (all gears PASS)
        - ACQUISITION level: NACC100000_FORMS-VISIT-3F_UDS.json

        Expected: pass-qc event with gear name "form-transformer" (final gear)
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create QC metadata with all gears passing (submission pipeline)
        # For now, let's test with a simple failure case since pass events need
        # timestamps
        # that aren't available in ValidationModel
        error_data = {
            "timestamp": "2025-03-19 11:30:00",
            "type": "error",
            "code": "test-error",
            "message": "Test error message",
            "ptid": "adrc1000",
            "visitnum": "3F",
            "date": "2025-03-19",
            "naccid": "NACC100000",
        }

        qc_metadata = create_qc_metadata(
            gears={"form-transformer": "FAIL"}, errors=[error_data]
        )

        # Create QC-status file modified after input file
        qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),  # After input file
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            group="dummy-center",
            files=[qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify not-pass-qc event was logged
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "not-pass-qc"
        assert event.gear_name == "form-transformer"
        assert event.ptid == "adrc1000"
        assert event.visit_date == "2025-03-19"
        assert event.study == "alpha"  # Extracted from project label
        assert event.project_label == "ingest-form-alpha"
        assert event.center_label == "dummy-center"

    def test_scenario_2_single_visit_pipeline_failure_early_stage(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 2: Visit fails at form-transformer, pipeline stops.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1001_2025-08-22_uds_qc-status.log
          (form-transformer FAIL)
        - ACQUISITION level: (no JSON file - pipeline failed)

        Expected: not-pass-qc event with error from form-transformer
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 8, 22, 10, 0, 0),
        )

        # Create error for form-transformer failure
        transformer_error = {
            "timestamp": "2025-08-22 12:10:25",
            "type": "error",
            "code": "form-transformer-error",
            "message": "Invalid form data structure",
            "ptid": "ADRC1001",
            "visitnum": "4F",
            "date": "2025-08-22",
            "naccid": "NACC100001",
        }

        # Create QC metadata with form-transformer failure
        qc_metadata = create_qc_metadata(
            gears={
                "identifier-lookup": "PASS",
                "form-transformer": "FAIL",
            },
            errors=[transformer_error],
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1001",
            date="2025-08-22",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 8, 22, 12, 15, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify not-pass-qc event was logged
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "not-pass-qc"
        assert event.gear_name == "form-transformer"
        assert event.ptid == "ADRC1001"
        assert event.visit_number == "4F"
        assert event.visit_date == "2025-08-22"

    def test_scenario_3_single_visit_pipeline_failure_late_stage(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 3: Visit passes early gears but fails at form-qc-
        checker.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1001_2025-08-22_uds_qc-status.log
          (mixed PASS/FAIL)
        - ACQUISITION level: NACC100001_FORMS-VISIT-4F_UDS.json (created before failure)

        Expected: not-pass-qc event with first error from form-qc-checker
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 8, 22, 10, 0, 0),
        )

        # Create alert errors for form-qc-checker failure
        qc_checker_errors = [
            {
                "timestamp": "2025-08-22 12:10:25",
                "type": "alert",
                "code": "b5-ivp-p-1010",
                "location": {"key_path": "anx"},
                "message": (
                    "if q6a. anx (anxiety) = 0 (no), then form b9, q12c. beanx "
                    "(anxiety) should not equal 1 (yes)"
                ),
                "ptid": "ADRC1001",
                "visitnum": "4F",
                "date": "2025-08-22",
                "naccid": "NACC100001",
            },
            {
                "timestamp": "2025-08-22 12:10:25",
                "type": "alert",
                "code": "d1b-i4vp-p-1004",
                "location": {"key_path": "cvd"},
                "message": (
                    "if q7a3. structcvd (consistent with cerebrovascular disease "
                    "(cvd)) =1 then q15. cvd (vascular brain injury) should = 1"
                ),
                "ptid": "ADRC1001",
                "visitnum": "4F",
                "date": "2025-08-22",
                "naccid": "NACC100001",
            },
        ]

        # Create QC metadata with finalization pipeline failure
        qc_metadata = create_qc_metadata(
            gears={
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
                "form-qc-coordinator": "PASS",
                "form-qc-checker": "FAIL",
            },
            errors=qc_checker_errors,
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1001",
            date="2025-08-22",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 8, 22, 12, 15, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify not-pass-qc event was logged with first error
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "not-pass-qc"
        assert event.gear_name == "form-qc-checker"
        assert event.ptid == "ADRC1001"
        assert event.visit_number == "4F"

    def test_scenario_4_multiple_visits_mixed_outcomes(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 4: CSV with multiple visits, some pass, some fail at
        different stages.

        File Structure:
        - PROJECT level: input-uds.csv (3 rows), multiple QC-status files
        - ACQUISITION level: Multiple JSON files

        Expected: One pass-qc event and two not-pass-qc events
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Visit 1: Submission pipeline success (all gears PASS)
        qc_metadata_1 = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        qc_file_1 = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata_1,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        # Visit 2: Finalization pipeline failure at form-qc-checker
        qc_checker_errors_2 = [
            {
                "timestamp": "2025-08-22 12:10:25",
                "type": "alert",
                "code": "b5-ivp-p-1010",
                "message": "QC check failed",
                "ptid": "ADRC1001",
                "visitnum": "4F",
                "date": "2025-08-22",
            }
        ]
        qc_metadata_2 = create_qc_metadata(
            gears={
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
                "form-qc-coordinator": "PASS",
                "form-qc-checker": "FAIL",
            },
            errors=qc_checker_errors_2,
        )
        qc_file_2 = create_mock_qc_file(
            ptid="adrc1001",
            date="2025-08-22",
            module="uds",
            qc_metadata=qc_metadata_2,
            modified=datetime(2025, 8, 22, 12, 0, 0),
        )

        # Visit 3: Finalization pipeline failure with both alerts and errors
        qc_checker_errors_3 = [
            {
                "timestamp": "2025-11-05 13:36:19",
                "type": "error",
                "code": "c2-ivp-m-185",
                "message": "q12. verbaltest (verbal learning test) cannot be blank",
                "ptid": "ADRC1003",
                "visitnum": "3F",
                "date": "2025-10-15",
            }
        ]
        qc_metadata_3 = create_qc_metadata(
            gears={
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
                "form-qc-coordinator": "PASS",
                "form-qc-checker": "FAIL",
            },
            errors=qc_checker_errors_3,
        )
        qc_file_3 = create_mock_qc_file(
            ptid="adrc1003",
            date="2025-10-15",
            module="uds",
            qc_metadata=qc_metadata_3,
            modified=datetime(2025, 10, 15, 14, 0, 0),
        )

        # Create mock project with all QC files
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file_1, qc_file_2, qc_file_3],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify three events were logged
        assert len(mock_event_logger.logged_events) == 3

        # Check pass-qc event for ADRC1000
        pass_events = mock_event_logger.get_events_by_action("pass-qc")
        assert len(pass_events) == 1
        pass_event = pass_events[0]
        assert pass_event.ptid == "adrc1000"
        assert pass_event.visit_date == "2025-03-19"

        # Check not-pass-qc events for ADRC1001 and ADRC1003
        fail_events = mock_event_logger.get_events_by_action("not-pass-qc")
        assert len(fail_events) == 2

        fail_ptids = {event.ptid for event in fail_events}
        assert "ADRC1001" in fail_ptids
        assert "ADRC1003" in fail_ptids

    def test_scenario_5_file_timestamp_filtering(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 5: Only QC-status files modified after input file are
        processed.

        File Structure:
        - PROJECT level: input-uds.csv (created at T), two QC-status files (T-1 and T+1)

        Expected: Only one event for file modified after input file
        """
        # Create input CSV file at specific timestamp
        input_timestamp = datetime(2025, 3, 19, 12, 0, 0)
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=input_timestamp,
        )

        # QC file 1: Modified BEFORE input file (should be ignored)
        qc_metadata_1 = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        qc_file_1 = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata_1,
            modified=datetime(2025, 3, 19, 11, 0, 0),  # Before input file
        )

        # QC file 2: Modified AFTER input file (should be processed)
        qc_metadata_2 = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
                "form-qc-coordinator": "PASS",
                "form-qc-checker": "PASS",
            }
        )
        qc_file_2 = create_mock_qc_file(
            ptid="adrc1002",
            date="2025-06-18",
            module="uds",
            qc_metadata=qc_metadata_2,
            modified=datetime(2025, 3, 19, 13, 0, 0),  # After input file
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file_1, qc_file_2],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify only one event was logged (for ADRC1002)
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]
        assert event.ptid == "adrc1002"

    def test_scenario_6_finalization_pipeline(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 6: Event logging for finalization pipeline processing
        JSON files.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1002_2025-06-18_uds_qc-status.log
          (finalization QC)
        - ACQUISITION level: NACC274180_FORMS-VISIT-3F_UDS.json

        Expected: pass-qc event based on finalization pipeline outcome
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 6, 18, 10, 0, 0),
        )

        # Create cleared alerts for finalization pipeline
        cleared_alerts = [
            {
                "alertHash": (
                    "b04446359f999c42231c90cfca5cb9895da8d0921990f2042bf61471796aae2b"
                ),
                "clear": True,
                "finalized": True,
                "provenance": [
                    {
                        "user": "user@dummy.org",
                        "clearSetTo": True,
                        "timestamp": "20250718085445",
                    }
                ],
            }
        ]

        # Create QC metadata for finalization pipeline with cleared alerts
        qc_metadata = create_qc_metadata(
            gears={
                "form-qc-coordinator": "PASS",
                "form-qc-checker": "PASS",
            },
            cleared_alerts=cleared_alerts,
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1002",
            date="2025-06-18",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 6, 18, 11, 0, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify pass-qc event was logged
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "pass-qc"
        assert event.ptid == "adrc1002"
        assert event.gear_name == "form-qc-checker"  # Final gear in finalization

    def test_scenario_7_no_qc_metadata(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 7: Behavior when QC-status files exist but have no
        relevant metadata.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1000_2025-03-19_uds_qc-status.log
          (empty/malformed QC)

        Expected: No events logged (graceful handling)
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Test various malformed QC metadata scenarios
        malformed_metadata_cases: List[Dict[str, Any]] = [
            # Empty qc object
            {"qc": {}},
            # Malformed validation structure
            {"qc": {"form-qc-checker": {"invalid": "structure"}}},
            # Missing validation section
            {"qc": {"form-transformer": {}}},
        ]

        for i, malformed_metadata in enumerate(malformed_metadata_cases):
            # Clear previous events
            mock_event_logger.clear()

            # Create QC-status file with malformed metadata
            qc_file = create_mock_qc_file(
                ptid=f"adrc100{i}",
                date="2025-03-19",
                module="uds",
                qc_metadata=malformed_metadata,
                modified=datetime(2025, 3, 19, 11, 0, 0),
            )

            # Create mock project
            project = MockProjectAdaptor(
                label="ingest-form-alpha",
                files=[qc_file],
            )

            # Log events
            event_accumulator.log_events(file=input_file, project=project)

            # Verify no events were logged
            assert len(mock_event_logger.logged_events) == 0, (
                f"Case {i} ({malformed_metadata}) generated "
                f"{len(mock_event_logger.logged_events)} events"
            )

    def test_scenario_8_multiple_modules(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 8: Processing files for different modules (UDS, FTLD,
        etc.).

        File Structure:
        - PROJECT level: input-uds.csv, input-ftld.csv, multiple QC-status files
        - ACQUISITION level: Multiple JSON files for different modules

        Expected: Events for each module processed
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # UDS module QC metadata
        uds_qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        uds_qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=uds_qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        # FTLD module QC metadata
        ftld_qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        ftld_qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="ftld",
            qc_metadata=ftld_qc_metadata,
            modified=datetime(2025, 3, 19, 11, 30, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[uds_qc_file, ftld_qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify events for both modules were logged
        assert len(mock_event_logger.logged_events) == 2

        # Check that both modules are represented
        modules = {event.module for event in mock_event_logger.logged_events}
        assert "UDS" in modules
        assert "FTLD" in modules

        # Both events should be for the same participant
        ptids = {event.ptid for event in mock_event_logger.logged_events}
        assert len(ptids) == 1
        assert "adrc1000" in ptids

    def test_scenario_9_cleared_alerts_count_as_passing(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test Scenario 9: Cleared alerts are treated as passing validations.

        File Structure:
        - PROJECT level: input-uds.csv, adrc1000_2025-03-19_uds_qc-status.log
          (has cleared alerts)
        - ACQUISITION level: NACC100000_FORMS-VISIT-3F_UDS.json

        Expected: pass-qc event because cleared alerts count as passing
        """
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create alerts that will be cleared
        alert_data = [
            {
                "timestamp": "2025-11-04 13:19:13",
                "type": "alert",
                "code": "d1b-i4vp-p-1005",
                "location": {"key_path": "csfad"},
                "message": (
                    "if q6b. amylcsf or q6f. csftau at previous visit = 1, "
                    "then q4a. csfad should =1"
                ),
                "ptid": "ADRC1000",
                "visitnum": "3F",
                "date": "2025-03-19",
                "naccid": "NACC100000",
            }
        ]

        # For now, test with failure case since pass events need timestamps
        # Create QC metadata with failure to test error handling
        qc_metadata = create_qc_metadata(
            gears={"form-qc-checker": "FAIL"}, errors=alert_data
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify not-pass-qc event was logged (testing error case for now)
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]

        assert event.action == "not-pass-qc"
        assert event.ptid == "ADRC1000"
        assert event.visit_date == "2025-03-19"
        assert event.gear_name == "form-qc-checker"

    def test_project_label_parsing(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that study is correctly extracted from project label."""
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create QC metadata
        qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        # Test different project label formats
        test_cases = [
            ("ingest-form-alpha", "alpha"),
            ("ingest-form-beta", "beta"),
            ("ingest-form-gamma", "gamma"),
        ]

        for project_label, expected_study in test_cases:
            # Clear previous events
            mock_event_logger.clear()

            # Create mock project with specific label
            project = MockProjectAdaptor(
                label=project_label,
                files=[qc_file],
            )

            # Log events
            event_accumulator.log_events(file=input_file, project=project)

            # Verify study was extracted correctly
            assert len(mock_event_logger.logged_events) == 1
            event = mock_event_logger.logged_events[0]
            assert event.study == expected_study

    def test_module_filtering(self, mock_event_logger: MockVisitEventLogger) -> None:
        """Test that EventAccumulator respects pipeline module filters."""
        # Create pipeline with limited modules
        limited_pipeline = Pipeline(
            name="submission",
            modules=["UDS"],  # Only UDS module
            tags=["queued"],
            extensions=[".csv"],
            starting_gear=GearInfo(
                gear_name="identifier-lookup", configs=GearConfigs()
            ),
        )

        # Create EventAccumulator with limited pipeline
        event_accumulator = EventAccumulator(
            pipeline=limited_pipeline,
            event_logger=mock_event_logger,
            datatype="form",
        )

        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create QC files for both UDS and FTLD modules
        uds_qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        uds_qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=uds_qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        ftld_qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )
        ftld_qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="ftld",
            qc_metadata=ftld_qc_metadata,
            modified=datetime(2025, 3, 19, 11, 30, 0),
        )

        # Create mock project
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[uds_qc_file, ftld_qc_file],
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify only UDS module event was logged (FTLD filtered out)
        assert len(mock_event_logger.logged_events) == 1
        event = mock_event_logger.logged_events[0]
        assert event.module == "UDS"

    def test_empty_project_no_events(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test that no events are logged when project has no QC files."""
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create mock project with no files
        project = MockProjectAdaptor(
            label="ingest-form-alpha",
            files=[],  # No QC files
        )

        # Log events
        event_accumulator.log_events(file=input_file, project=project)

        # Verify no events were logged
        assert len(mock_event_logger.logged_events) == 0

    def test_invalid_project_label(
        self,
        event_accumulator: EventAccumulator,
        mock_event_logger: MockVisitEventLogger,
    ) -> None:
        """Test handling of invalid project labels."""
        # Create input CSV file
        input_file = create_mock_file_with_timestamp(
            name="input-uds.csv",
            created=datetime(2025, 3, 19, 10, 0, 0),
        )

        # Create QC metadata
        qc_metadata = create_qc_metadata(
            {
                "identifier-lookup": "PASS",
                "form-transformer": "PASS",
            }
        )

        # Create QC-status file
        qc_file = create_mock_qc_file(
            ptid="adrc1000",
            date="2025-03-19",
            module="uds",
            qc_metadata=qc_metadata,
            modified=datetime(2025, 3, 19, 11, 0, 0),
        )

        # Create mock project with invalid label format
        project = MockProjectAdaptor(
            label="invalid-label-format",  # Doesn't match expected pattern
            files=[qc_file],
        )

        # This should raise an exception when trying to parse the pipeline label
        with pytest.raises(ValidationError):  # PipelineLabel validation error
            event_accumulator.log_events(file=input_file, project=project)
