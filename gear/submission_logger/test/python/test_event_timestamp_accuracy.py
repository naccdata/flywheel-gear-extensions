"""Property-based tests for event timestamp accuracy in submission logger."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.event_logger import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import FileErrorList
from outputs.error_writer import ListErrorWriter
from submission_logger_app.main import run


@st.composite
def timestamp_test_data(draw):
    """Generate test data with specific timestamp for testing."""
    # Generate a timestamp within reasonable bounds
    base_time = datetime(2024, 1, 1, 12, 0, 0)
    offset_seconds = draw(
        st.integers(min_value=0, max_value=365 * 24 * 3600)
    )  # Up to 1 year
    timestamp = base_time + timedelta(seconds=offset_seconds)

    # Generate simple CSV data
    ptid = draw(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(min_codepoint=33, max_codepoint=126).filter(
                lambda c: c not in ',"\n\r'
            ),
        )
    )
    visitdate = draw(
        st.dates(
            min_value=datetime(2020, 1, 1).date(),
            max_value=datetime(2024, 12, 31).date(),
        )
    ).strftime("%Y-%m-%d")
    visitnum = draw(st.integers(min_value=1, max_value=99))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD"]))
    packet = draw(st.sampled_from(["I", "F"]))
    adcid = draw(st.integers(min_value=1, max_value=99))

    return {
        "timestamp": timestamp,
        "csv_data": {
            "ptid": ptid,
            "visitdate": visitdate,
            "visitnum": str(visitnum),
            "module": module,
            "packet": packet,
            "adcid": str(adcid),
        },
    }


def create_csv_content(visit_data: dict[str, Any]) -> str:
    """Create CSV content from visit data."""
    headers = list(visit_data.keys())
    values = list(visit_data.values())

    header_line = ",".join(headers)
    value_line = ",".join(str(v) for v in values)

    return f"{header_line}\n{value_line}"


def create_mock_module_configs() -> ModuleConfigs:
    """Create mock module configurations."""
    from configs.ingest_configs import LabelTemplate, UploadTemplateInfo

    return ModuleConfigs(
        initial_packets=["I"],
        followup_packets=["F"],
        versions=["3.0"],
        date_field="visitdate",
        hierarchy_labels=UploadTemplateInfo(
            session=LabelTemplate(template="test-session"),
            acquisition=LabelTemplate(template="test-acquisition"),
            filename=LabelTemplate(template="test-filename"),
        ),
        required_fields=["ptid", "visitdate", "visitnum", "module", "packet", "adcid"],
    )


def create_mock_form_project_configs(module: str) -> FormProjectConfigs:
    """Create mock form project configurations."""
    return FormProjectConfigs(
        primary_key="ptid",
        accepted_modules=[module],
        module_configs={module: create_mock_module_configs()},
    )


class TestEventTimestampAccuracy:
    """Property-based tests for event timestamp accuracy."""

    @given(test_data=timestamp_test_data())
    @settings(max_examples=100, deadline=None)
    def test_event_timestamp_accuracy(self, test_data):
        """**Feature: submission-logger, Property 3: Event Timestamp Accuracy**

        For any submit event created, the event timestamp should match the file
        upload timestamp within acceptable precision bounds.
        **Validates: Requirements 1.4**
        """
        timestamp = test_data["timestamp"]
        csv_data = test_data["csv_data"]

        # Create CSV content
        csv_content = create_csv_content(csv_data)

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write(csv_content)
            temp_file_path = temp_file.name

        try:
            # Mock dependencies
            mock_event_logger = Mock(spec=VisitEventLogger)
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input with specific timestamp
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with the test timestamp
            mock_file_entry = Mock()
            mock_file_entry.created = timestamp
            mock_file_input.file_entry.return_value = mock_file_entry

            # Mock project adaptor
            mock_project = Mock(spec=ProjectAdaptor)
            mock_project.group = "test-center"
            mock_project.label = "test-project"
            mock_file_input.get_parent_project.return_value = Mock()

            # Mock update_error_log_and_qc_metadata to avoid actual file operations
            with (
                patch(
                    "submission_logger_app.main.ProjectAdaptor",
                    return_value=mock_project,
                ),
                patch(
                    "submission_logger_app.qc_status_log_creator.update_error_log_and_qc_metadata"
                ) as mock_update_qc,
            ):
                mock_update_qc.return_value = True

                # Create form project configs
                module = csv_data["module"]
                form_project_configs = create_mock_form_project_configs(module)

                # Run the submission logger
                success = run(
                    file_input=mock_file_input,
                    event_logger=mock_event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=form_project_configs,
                    module=module,
                )

                # Verify success
                assert success, "Processing should succeed for valid CSV data"

                # Verify that log_event was called exactly once
                assert mock_event_logger.log_event.call_count == 1, (
                    "Expected exactly one event to be logged"
                )

                # Get the logged event
                logged_event_call = mock_event_logger.log_event.call_args
                assert logged_event_call is not None, (
                    "log_event should have been called"
                )

                logged_event = logged_event_call[0][0]  # First positional argument

                # Verify the timestamp matches exactly
                assert logged_event.timestamp == timestamp, (
                    f"Event timestamp {logged_event.timestamp} should match "
                    f"file upload timestamp {timestamp}"
                )

                # Verify other event properties are correct
                assert logged_event.action == "submit", "Action should be 'submit'"
                assert logged_event.ptid == csv_data["ptid"], (
                    "PTID should match CSV data"
                )
                assert logged_event.visit_date == csv_data["visitdate"], (
                    "Visit date should match CSV data"
                )
                assert logged_event.visit_number == csv_data["visitnum"], (
                    "Visit number should match CSV data"
                )
                assert logged_event.module == csv_data["module"], (
                    "Module should match CSV data"
                )
                assert logged_event.packet == csv_data["packet"], (
                    "Packet should match CSV data"
                )
                assert logged_event.pipeline_adcid == int(csv_data["adcid"]), (
                    "ADCID should match CSV data"
                )

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_timestamp_precision_edge_cases(self):
        """Test timestamp precision with edge cases like microseconds."""
        # Test with microsecond precision
        timestamp_with_microseconds = datetime(2024, 6, 15, 14, 30, 45, 123456)

        csv_data = {
            "ptid": "TEST001",
            "visitdate": "2024-06-15",
            "visitnum": "1",
            "module": "UDS",
            "packet": "I",
            "adcid": "42",
        }

        csv_content = create_csv_content(csv_data)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write(csv_content)
            temp_file_path = temp_file.name

        try:
            # Mock dependencies
            mock_event_logger = Mock(spec=VisitEventLogger)
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with microsecond precision timestamp
            mock_file_entry = Mock()
            mock_file_entry.created = timestamp_with_microseconds
            mock_file_input.file_entry.return_value = mock_file_entry

            # Mock project adaptor
            mock_project = Mock(spec=ProjectAdaptor)
            mock_project.group = "test-center"
            mock_project.label = "test-project"
            mock_file_input.get_parent_project.return_value = Mock()

            with (
                patch(
                    "submission_logger_app.main.ProjectAdaptor",
                    return_value=mock_project,
                ),
                patch(
                    "submission_logger_app.qc_status_log_creator.update_error_log_and_qc_metadata"
                ) as mock_update_qc,
            ):
                mock_update_qc.return_value = True

                # Create form project configs
                form_project_configs = create_mock_form_project_configs("UDS")

                # Run the submission logger
                success = run(
                    file_input=mock_file_input,
                    event_logger=mock_event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=form_project_configs,
                    module="UDS",
                )

                # Verify success
                assert success, "Processing should succeed"

                # Verify timestamp precision is preserved
                assert mock_event_logger.log_event.call_count == 1
                logged_event = mock_event_logger.log_event.call_args[0][0]

                assert logged_event.timestamp == timestamp_with_microseconds, (
                    f"Microsecond precision should be preserved: "
                    f"expected {timestamp_with_microseconds}, "
                    f"got {logged_event.timestamp}"
                )

        finally:
            Path(temp_file_path).unlink(missing_ok=True)
