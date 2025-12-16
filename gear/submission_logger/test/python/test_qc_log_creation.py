"""Property-based tests for QC status log creation in submission logger."""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.event_logging import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import FileErrorList, VisitKeys
from outputs.error_writer import ListErrorWriter
from submission_logger_app.main import run
from submission_logger_app.qc_status_log_creator import QCStatusLogCreator


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


class TestQCLogCreation:
    """Property-based tests for QC status log creation."""

    @given(csv_data=csv_data_generator())
    @settings(max_examples=100, deadline=None)
    def test_qc_status_log_creation_consistency(self, csv_data):
        """**Feature: submission-logger, Property 2: QC Status Log Creation**

        For any visit identified in an uploaded file, a corresponding QC status
        log file should be created at the project level using the ErrorLogTemplate
        naming pattern.
        **Validates: Requirements 3.1, 3.2**
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

            # Mock update_error_log_and_qc_metadata to track QC log creation calls
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
                expected_qc_logs = 0
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
                        expected_qc_logs += 1

                # Verify update_error_log_and_qc_metadata was called for each visit
                actual_qc_logs = mock_update_qc.call_count
                assert actual_qc_logs == expected_qc_logs, (
                    f"Expected {expected_qc_logs} QC status logs to be created, "
                    f"but {actual_qc_logs} were created"
                )

                # Verify that each call used the correct ErrorLogTemplate naming pattern
                for call in mock_update_qc.call_args_list:
                    kwargs = call.kwargs
                    error_log_name = kwargs["error_log_name"]

                    # QC log pattern: {ptid}_{visitdate}_{module}_qc-status.log
                    assert error_log_name.endswith("_qc-status.log"), (
                        f"QC log name should end with '_qc-status.log': "
                        f"{error_log_name}"
                    )

                    # Should contain ptid, visitdate, and module
                    parts = error_log_name.replace("_qc-status.log", "").split("_")
                    assert len(parts) >= 3, (
                        f"QC log name should have at least 3 parts "
                        f"(ptid_visitdate_module): {error_log_name}"
                    )

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_qc_log_creator_direct(self):
        """Test QCStatusLogCreator directly with VisitKeys."""
        # Create test visit keys
        visit_keys = VisitKeys(
            ptid="TEST001",
            date="2024-01-15",
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Create QC status log creator
        error_log_template = ErrorLogTemplate()
        mock_visit_annotator = Mock()
        mock_visit_annotator.annotate_qc_log_file.return_value = True
        qc_log_creator = QCStatusLogCreator(error_log_template, mock_visit_annotator)

        # Mock project and error writer
        mock_project = Mock(spec=ProjectAdaptor)
        mock_error_writer = Mock(spec=ListErrorWriter)
        mock_error_writer.errors.return_value = FileErrorList(root=[])

        # Mock update_error_log_and_qc_metadata
        with patch(
            "submission_logger_app.qc_status_log_creator.update_error_log_and_qc_metadata"
        ) as mock_update_qc:
            mock_update_qc.return_value = True

            # Create QC log
            success = qc_log_creator.create_qc_log(
                visit_keys=visit_keys,
                project=mock_project,
                gear_name="test-gear",
                error_writer=mock_error_writer,
            )

            # Verify success
            assert success, "QC log creation should succeed"

            # Verify update_error_log_and_qc_metadata was called
            mock_update_qc.assert_called_once()

            # Verify the call arguments
            call_kwargs = mock_update_qc.call_args.kwargs
            assert call_kwargs["gear_name"] == "test-gear"
            assert call_kwargs["state"] == "PASS"
            assert call_kwargs["reset_qc_metadata"] == "ALL"

            # Verify the error log name follows the pattern
            error_log_name = call_kwargs["error_log_name"]
            assert error_log_name == "TEST001_2024-01-15_uds_qc-status.log"

            # Verify that visit annotation was called
            mock_visit_annotator.annotate_qc_log_file.assert_called_once_with(
                qc_log_filename=error_log_name, visit_keys=visit_keys
            )

    def test_qc_log_creator_insufficient_data(self):
        """Test QCStatusLogCreator with insufficient visit data."""
        # Create visit keys with missing data
        visit_keys = VisitKeys(
            ptid="TEST001",
            date=None,  # Missing date
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Create QC status log creator
        error_log_template = ErrorLogTemplate()
        mock_visit_annotator = Mock()
        qc_log_creator = QCStatusLogCreator(error_log_template, mock_visit_annotator)

        # Mock project and error writer
        mock_project = Mock(spec=ProjectAdaptor)
        mock_error_writer = Mock(spec=ListErrorWriter)
        mock_error_writer.errors.return_value = FileErrorList(root=[])

        # Create QC log
        success = qc_log_creator.create_qc_log(
            visit_keys=visit_keys,
            project=mock_project,
            gear_name="test-gear",
            error_writer=mock_error_writer,
        )

        # Should fail due to missing date
        assert not success, "QC log creation should fail with insufficient data"

    def test_get_qc_log_filename(self):
        """Test QC log filename generation."""
        # Create test visit keys
        visit_keys = VisitKeys(
            ptid="TEST001",
            date="2024-01-15",
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Create QC status log creator
        error_log_template = ErrorLogTemplate()
        mock_visit_annotator = Mock()
        qc_log_creator = QCStatusLogCreator(error_log_template, mock_visit_annotator)

        # Get filename
        filename = qc_log_creator.get_qc_log_filename(visit_keys)

        # Verify filename
        assert filename == "TEST001_2024-01-15_uds_qc-status.log"

        # Test with insufficient data
        incomplete_visit_keys = VisitKeys(
            ptid="TEST001",
            date=None,  # Missing date
            module="UDS",
        )

        filename = qc_log_creator.get_qc_log_filename(incomplete_visit_keys)
        assert filename is None, "Should return None for incomplete visit data"

    @given(csv_data=csv_data_generator())
    @settings(max_examples=100, deadline=None)
    def test_file_content_preservation(self, csv_data):
        """**Feature: submission-logger, Property 4: File Content Preservation**

        For any uploaded file processed successfully, the original file content
        should remain unchanged. No visit metadata should be added to the uploaded file.
        **Validates: Requirements 4.1, 4.2**
        """
        # Create CSV content
        csv_content = create_csv_content(csv_data)
        original_content = csv_content

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

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with created timestamp and update_info method
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
            mock_file_entry.update_info = Mock()
            mock_file_input.file_entry.return_value = mock_file_entry

            # Mock project adaptor
            mock_project = Mock(spec=ProjectAdaptor)
            mock_project.group = "test-center"
            mock_project.label = "test-project"
            mock_file_input.get_parent_project.return_value = Mock()

            # Mock update_error_log_and_qc_metadata
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
                module = csv_data[0]["module"]
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

                # Verify that the original file content is unchanged
                with open(temp_file_path, "r", encoding="utf-8") as f:
                    current_content = f.read()
                assert current_content == original_content, (
                    "Original file content should remain unchanged"
                )

                # Count expected valid visits
                expected_visits = 0
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
                        expected_visits += 1

                # Verify NO metadata was added to uploaded file (per user requirement)
                mock_file_entry.update_info.assert_not_called()

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)
