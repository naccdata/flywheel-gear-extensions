"""Property-based tests for CSV event creation in submission logger."""

import tempfile
from datetime import datetime
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
from submission_logger_app.main import ConfigurationError, FileProcessingError, run


# Hypothesis strategies for generating test data
@st.composite
def csv_visit_data(draw):
    """Generate valid CSV visit data using Hypothesis strategies."""
    # PTID must match pattern '^[!-~]{1,10}' (printable ASCII chars, 1-10 length)
    # Exclude CSV problematic characters: comma, quote, newline
    # Also avoid PTIDs that are all zeros (they get stripped to empty string)
    ptid_chars = st.characters(min_codepoint=33, max_codepoint=126).filter(
        lambda c: c not in ',"\n\r'
    )
    ptid = draw(
        st.text(min_size=1, max_size=10, alphabet=ptid_chars).filter(
            lambda s: s.strip().lstrip("0")
            != ""  # Avoid PTIDs that become empty after stripping zeros
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
        "ptid": ptid,
        "visitdate": visitdate,
        "visitnum": str(visitnum),
        "module": module,
        "packet": packet,
        "adcid": str(adcid),
    }


@st.composite
def csv_data_generator(draw):
    """Generate CSV data with multiple visits using Hypothesis."""
    num_visits = draw(st.integers(min_value=1, max_value=5))
    visits = [draw(csv_visit_data()) for _ in range(num_visits)]
    return visits


def create_csv_content(visits: list[dict[str, Any]]) -> str:
    """Create CSV content from visit data."""
    if not visits:
        return ""

    headers = list(visits[0].keys())
    lines = [",".join(headers)]

    for visit in visits:
        line = ",".join(str(visit.get(header, "")) for header in headers)
        lines.append(line)

    return "\n".join(lines)


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


class TestCSVEventCreation:
    """Property-based tests for CSV event creation."""

    @given(csv_data=csv_data_generator())
    @settings(max_examples=100, deadline=None)
    def test_visit_event_creation_completeness(self, csv_data):
        """**Feature: submission-logger, Property 1: Visit Event Creation Completeness**

        For any uploaded file containing visit data, the number of submit events
        logged should equal the number of valid visits extracted from the file.
        **Validates: Requirements 1.2, 2.5**
        """
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
            # Mock error_writer.errors() to return empty FileErrorList
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with created timestamp
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
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
                module = csv_data[0]["module"]  # Use module from first visit
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

                # Count expected valid visits (visits with all required fields)
                expected_events = 0
                for visit in csv_data:
                    if all(
                        visit.get(field)
                        for field in [
                            "ptid",
                            "visitdate",
                            "visitnum",
                            "module",
                            "packet",
                            "adcid",
                        ]
                    ):
                        expected_events += 1

                # Verify that log_event was called the expected number of times
                actual_events = mock_event_logger.log_event.call_count
                assert actual_events == expected_events, (
                    f"Expected {expected_events} events to be logged, "
                    f"but {actual_events} were logged"
                )

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_empty_csv_handling(self):
        """Test that empty CSV files are handled gracefully."""
        # Create empty CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write("")
            temp_file_path = temp_file.name

        try:
            # Mock dependencies
            mock_event_logger = Mock(spec=VisitEventLogger)
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            # Mock error_writer.errors() to return empty FileErrorList
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "empty.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
            mock_file_input.file_entry.return_value = mock_file_entry

            # Mock project adaptor
            mock_project = Mock(spec=ProjectAdaptor)
            mock_project.group = "test-center"
            mock_project.label = "test-project"
            mock_file_input.get_parent_project.return_value = Mock()

            with patch(
                "submission_logger_app.main.ProjectAdaptor", return_value=mock_project
            ):
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

                # Should handle empty file gracefully (return False but not crash)
                assert not success, "Empty CSV should return False"

                # No events should be logged for empty file
                assert mock_event_logger.log_event.call_count == 0, (
                    "No events should be logged for empty file"
                )

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    @given(file_extension=st.sampled_from(["csv", "txt", "json", "xlsx", ""]))
    @settings(max_examples=50, deadline=None)
    def test_dynamic_dispatch_correctness(self, file_extension):
        """**Feature: submission-logger, Property 6: Dynamic Dispatch Correctness**

        For any supported file type, the dispatcher should select exactly one
        appropriate processor that can handle that file type.
        **Validates: Technical Architecture Constraint 1**
        """
        # Determine expected result based on file extension
        expected_result = file_extension == "csv"

        # Create test file with specified extension
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f".{file_extension}" if file_extension else "",
            delete=False,
        ) as temp_file:
            temp_file.write("test,content\n1,2")
            temp_file_path = temp_file.name

        try:
            # Mock dependencies
            mock_event_logger = Mock(spec=VisitEventLogger)
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            # Mock error_writer.errors() to return empty FileErrorList
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = (
                f"test.{file_extension}" if file_extension else "test"
            )
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = (
                "csv" if expected_result else None
            )

            # Mock file entry
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
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
                if expected_result:
                    # For CSV files, should process without raising exception
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
                    # CSV files are processed, not rejected
                    mock_file_input.validate_file_extension.assert_called_with(["csv"])
                else:
                    # For non-CSV files, should raise FileProcessingError
                    try:
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
                        # Should not reach here for unsupported files
                        assert False, (
                            f"Should raise FileProcessingError for {file_extension} files"
                        )
                    except FileProcessingError:
                        # Expected behavior for unsupported file types
                        pass

                    mock_file_input.validate_file_extension.assert_called_with(["csv"])
                    # Event logger should not be called for unsupported files
                    mock_event_logger.log_event.assert_not_called()

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_no_form_config_handling(self):
        """Test that the gear returns error when no form config is provided for
        CSV files."""
        # Create test CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write("col1,col2\nvalue1,value2")
            temp_file_path = temp_file.name

        try:
            # Mock dependencies
            mock_event_logger = Mock(spec=VisitEventLogger)
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            # Mock error_writer.errors() to return empty FileErrorList
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
            mock_file_input.file_entry.return_value = mock_file_entry

            # Run the submission logger without form configs
            try:
                success = run(
                    file_input=mock_file_input,
                    event_logger=mock_event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=None,  # No form config provided
                    module=None,  # No module provided
                )
                # Should not reach here - should raise ConfigurationError
                assert False, (
                    "Should raise ConfigurationError when form config is missing"
                )
            except ConfigurationError:
                # Expected behavior - configuration error should be raised
                pass

            # No events should be logged since processing failed
            assert mock_event_logger.log_event.call_count == 0, (
                "No events should be logged when processing fails"
            )

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)
