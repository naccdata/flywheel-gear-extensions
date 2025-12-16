"""Debug test to understand metrics tracking."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.event_logger import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from nacc_common.error_models import FileErrorList
from outputs.error_writer import ListErrorWriter
from submission_logger_app.main import run


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


def test_debug_single_visit():
    """Debug test with a single visit to understand what's happening."""
    # Create simple CSV with one visit
    csv_content = (
        "ptid,visitdate,visitnum,module,packet,adcid\ntest1,2023-01-01,1,UDS,I,1\n"
    )

    # Create temporary CSV file
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
                "error_logging.error_logger.update_error_log_and_qc_metadata"
            ) as mock_update_qc,
        ):
            # Mock QC log creation to succeed
            mock_update_qc.return_value = True

            # Create form project configs
            form_project_configs = create_mock_form_project_configs("UDS")

            # Capture the global metrics before running
            # Reset metrics for clean test
            from metrics.processing_metrics import ProcessingMetrics
            from submission_logger_app.main import _processing_metrics

            _processing_metrics = ProcessingMetrics()

            print(f"Before run: visits_found = {_processing_metrics.visits_found}")

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

            print(f"After run: success = {success}")
            print(f"After run: visits_found = {_processing_metrics.visits_found}")
            print(
                f"After run: visits_processed_successfully = {_processing_metrics.visits_processed_successfully}"
            )
            print(f"After run: visits_failed = {_processing_metrics.visits_failed}")
            print(f"After run: events_created = {_processing_metrics.events_created}")
            print(f"After run: qc_logs_created = {_processing_metrics.qc_logs_created}")
            print(
                f"After run: errors_encountered = {_processing_metrics.errors_encountered}"
            )
            print(f"After run: error_types = {_processing_metrics.error_types}")

            # Check if event logger was called
            print(f"Event logger call count: {mock_event_logger.log_event.call_count}")
            print(
                f"Error writer write call count: {mock_error_writer.write.call_count}"
            )

            # Get final metrics
            metrics_dict = _processing_metrics.get_metrics_dict()
            print(f"Final metrics dict: {metrics_dict}")

    finally:
        # Clean up temporary file
        Path(temp_file_path).unlink(missing_ok=True)


if __name__ == "__main__":
    test_debug_single_visit()
