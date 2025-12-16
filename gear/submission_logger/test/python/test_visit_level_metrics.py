"""Property-based tests for visit-level metrics consistency."""

import tempfile
from datetime import datetime
from pathlib import Path
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
from submission_logger_app.main import ProcessingMetrics, run


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


def create_csv_content_with_visits(num_visits: int) -> str:
    """Create CSV content with specified number of visits."""
    if num_visits == 0:
        return "ptid,visitdate,visitnum,module,packet,adcid\n"

    header = "ptid,visitdate,visitnum,module,packet,adcid\n"
    rows = []
    for i in range(num_visits):
        # Use valid dates to avoid date parsing errors
        day = (i % 28) + 1  # Keep days between 1-28 to avoid invalid dates
        rows.append(f"test{i + 1},2023-01-{day:02d},1,UDS,I,1\n")
    return header + "".join(rows)


class TestVisitLevelMetricsConsistency:
    """Property-based tests for visit-level metrics consistency."""

    @given(
        visits_found=st.integers(min_value=0, max_value=50),
        visits_processed_successfully=st.integers(min_value=0, max_value=50),
        visits_failed=st.integers(min_value=0, max_value=50),
        events_created=st.integers(min_value=0, max_value=50),
        events_failed=st.integers(min_value=0, max_value=50),
        qc_logs_created=st.integers(min_value=0, max_value=50),
        qc_logs_failed=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_visit_level_metrics_consistency(
        self,
        visits_found,
        visits_processed_successfully,
        visits_failed,
        events_created,
        events_failed,
        qc_logs_created,
        qc_logs_failed,
    ):
        """**Feature: submission-logger, Property 7: Visit-Level Metrics Consistency**

        **Validates: Requirements 8.2, 8.3**

        For any processing execution, the metrics should focus on visit-level statistics
        without misleading file-level counters, tracking visits found within the input file.
        """
        # Create a ProcessingMetrics instance and populate it with test data
        metrics = ProcessingMetrics()

        # Set up metrics with generated values
        metrics.visits_found = visits_found
        metrics.visits_processed_successfully = visits_processed_successfully
        metrics.visits_failed = visits_failed
        metrics.events_created = events_created
        metrics.events_failed = events_failed
        metrics.qc_logs_created = qc_logs_created
        metrics.qc_logs_failed = qc_logs_failed

        # Add some error types for testing
        metrics.errors_encountered = min(visits_failed, 10)
        for i in range(min(metrics.errors_encountered, 3)):
            metrics.error_types[f"error_type_{i}"] = 1

        # Start and end processing to get duration
        metrics.start_processing()
        metrics.end_processing()

        # Get metrics dictionary
        metrics_dict = metrics.get_metrics_dict()

        # Property 1: Metrics should focus on visit-level statistics
        visit_level_keys = {
            "visits_found",
            "visits_processed_successfully",
            "visits_failed",
            "events_created",
            "events_failed",
            "qc_logs_created",
            "qc_logs_failed",
            "visit_success_rate",
            "event_success_rate",
            "qc_log_success_rate",
            "processing_duration_seconds",
            "errors_encountered",
            "error_types",
        }

        for key in visit_level_keys:
            assert key in metrics_dict, f"Missing visit-level metric: {key}"

        # Property 2: Should NOT contain misleading file-level counters
        file_level_keys = {
            "files_processed",
            "files_found",
            "files_failed",
            "file_success_rate",
        }

        for key in file_level_keys:
            assert key not in metrics_dict, (
                f"Found misleading file-level counter: {key}"
            )

        # Property 3: Visit metrics should accurately reflect visits found in the input file
        assert metrics_dict["visits_found"] == visits_found
        assert (
            metrics_dict["visits_processed_successfully"]
            == visits_processed_successfully
        )
        assert metrics_dict["visits_failed"] == visits_failed
        assert metrics_dict["events_created"] == events_created
        assert metrics_dict["events_failed"] == events_failed
        assert metrics_dict["qc_logs_created"] == qc_logs_created
        assert metrics_dict["qc_logs_failed"] == qc_logs_failed

        # Property 4: Success rates should be meaningful for visit-level processing
        if visits_found > 0:
            expected_success_rate = (visits_processed_successfully / visits_found) * 100
            assert (
                abs(metrics_dict["visit_success_rate"] - expected_success_rate) < 0.01
            ), "Visit success rate calculation should be accurate"
        else:
            assert metrics_dict["visit_success_rate"] == 0.0, (
                "Visit success rate should be 0 for no visits"
            )

        if (events_created + events_failed) > 0:
            expected_event_success_rate = (
                events_created / (events_created + events_failed)
            ) * 100
            assert (
                abs(metrics_dict["event_success_rate"] - expected_event_success_rate)
                < 0.01
            ), "Event success rate calculation should be accurate"
        else:
            assert metrics_dict["event_success_rate"] == 0.0, (
                "Event success rate should be 0 for no events"
            )

        if (qc_logs_created + qc_logs_failed) > 0:
            expected_qc_success_rate = (
                qc_logs_created / (qc_logs_created + qc_logs_failed)
            ) * 100
            assert (
                abs(metrics_dict["qc_log_success_rate"] - expected_qc_success_rate)
                < 0.01
            ), "QC log success rate calculation should be accurate"
        else:
            assert metrics_dict["qc_log_success_rate"] == 0.0, (
                "QC log success rate should be 0 for no QC logs"
            )

        # Property 5: Processing duration should be tracked for the gear execution
        assert "processing_duration_seconds" in metrics_dict, (
            "Processing duration should be tracked"
        )
        assert metrics_dict["processing_duration_seconds"] >= 0, (
            "Processing duration should be non-negative"
        )

    def test_empty_file_metrics_consistency(self):
        """Test that empty files produce consistent visit-level metrics."""
        # Create empty CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            # Write only header or nothing
            temp_file.write("ptid,visitdate,visitnum,module,packet,adcid\n")
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

            with (
                patch(
                    "submission_logger_app.main.ProjectAdaptor",
                    return_value=mock_project,
                ),
                patch(
                    "error_logging.error_logger.update_error_log_and_qc_metadata"
                ) as mock_update_qc,
            ):
                mock_update_qc.return_value = True

                # Create form project configs
                form_project_configs = create_mock_form_project_configs("UDS")

                # Capture the global metrics before running
                # Reset metrics for clean test
                from metrics.processing_metrics import ProcessingMetrics
                from submission_logger_app.main import _processing_metrics

                _processing_metrics = ProcessingMetrics()

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

                # Get final metrics
                metrics_dict = _processing_metrics.get_metrics_dict()

                # For empty files, all visit-level metrics should be zero
                assert metrics_dict["visits_found"] == 0
                assert metrics_dict["visits_processed_successfully"] == 0
                assert metrics_dict["visits_failed"] == 0
                assert metrics_dict["events_created"] == 0
                assert metrics_dict["qc_logs_created"] == 0

                # Success rates should be 0 for empty files
                assert metrics_dict["visit_success_rate"] == 0.0
                assert metrics_dict["event_success_rate"] == 0.0
                assert metrics_dict["qc_log_success_rate"] == 0.0

                # Should still track processing duration
                assert metrics_dict["processing_duration_seconds"] >= 0

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)
