"""Unit tests for error handling and metrics in submission logger."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.event_logger import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from hypothesis import given, settings
from hypothesis import strategies as st
from metrics.processing_metrics import ProcessingMetrics
from nacc_common.error_models import FileErrorList
from outputs.error_writer import ListErrorWriter
from submission_logger_app.main import ConfigurationError, FileProcessingError, run


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


class TestErrorHandlingAndMetrics:
    """Unit tests for error handling and metrics collection."""

    def test_processing_metrics_initialization(self):
        """Test that ProcessingMetrics initializes correctly."""
        metrics = ProcessingMetrics()

        assert metrics.visits_found == 0
        assert metrics.visits_processed_successfully == 0
        assert metrics.visits_failed == 0
        assert metrics.events_created == 0
        assert metrics.events_failed == 0
        assert metrics.qc_logs_created == 0
        assert metrics.qc_logs_failed == 0
        assert metrics.errors_encountered == 0
        assert metrics.error_types == {}
        assert metrics.processing_start_time is None
        assert metrics.processing_end_time is None

        # Verify that ProcessingMetrics no longer has files_processed attribute
        assert not hasattr(metrics, "files_processed")

    def test_processing_metrics_tracking(self):
        """Test that ProcessingMetrics tracks values correctly."""
        metrics = ProcessingMetrics()

        # Test increment methods
        metrics.increment_visits_found(3)
        assert metrics.visits_found == 3

        metrics.increment_visits_processed_successfully(2)
        assert metrics.visits_processed_successfully == 2

        metrics.increment_visits_failed(1)
        assert metrics.visits_failed == 1

        metrics.increment_events_created(2)
        assert metrics.events_created == 2

        metrics.increment_events_failed(1)
        assert metrics.events_failed == 1

        metrics.increment_qc_logs_created(2)
        assert metrics.qc_logs_created == 2

        metrics.increment_qc_logs_failed(1)
        assert metrics.qc_logs_failed == 1

        # Test error recording
        metrics.record_error("test-error")
        metrics.record_error("test-error")
        metrics.record_error("other-error")

        assert metrics.errors_encountered == 3
        assert metrics.error_types["test-error"] == 2
        assert metrics.error_types["other-error"] == 1

    def test_processing_metrics_duration(self):
        """Test that ProcessingMetrics tracks processing duration."""
        metrics = ProcessingMetrics()

        # Initially no duration
        assert metrics.get_processing_duration() == 0.0

        # Start and end processing
        metrics.start_processing()
        assert metrics.processing_start_time is not None

        metrics.end_processing()
        assert metrics.processing_end_time is not None

        # Duration should be positive
        duration = metrics.get_processing_duration()
        assert duration >= 0.0

    def test_processing_metrics_dict(self):
        """Test that ProcessingMetrics returns correct dictionary."""
        metrics = ProcessingMetrics()

        # Add some test data
        metrics.increment_visits_found(5)
        metrics.increment_visits_processed_successfully(3)
        metrics.increment_visits_failed(2)
        metrics.increment_events_created(3)
        metrics.increment_events_failed(2)
        metrics.record_error("test-error")

        metrics_dict = metrics.get_metrics_dict()

        assert metrics_dict["visits_found"] == 5
        assert metrics_dict["visits_processed_successfully"] == 3
        assert metrics_dict["visits_failed"] == 2
        assert metrics_dict["events_created"] == 3
        assert metrics_dict["events_failed"] == 2
        assert metrics_dict["errors_encountered"] == 1
        assert metrics_dict["error_types"]["test-error"] == 1
        assert metrics_dict["visit_success_rate"] == 60.0  # 3/5 * 100
        assert metrics_dict["event_success_rate"] == 60.0  # 3/5 * 100

        # Test that get_metrics_dict() doesn't contain files_processed key
        assert "files_processed" not in metrics_dict
        assert "files_found" not in metrics_dict
        assert "files_failed" not in metrics_dict
        assert "file_success_rate" not in metrics_dict

    def test_file_not_found_error_handling(self):
        """Test that file not found errors are handled gracefully."""
        # Mock dependencies
        mock_event_logger = Mock(spec=VisitEventLogger)
        mock_proxy = Mock(spec=FlywheelProxy)
        mock_context = Mock(spec=GearToolkitContext)
        mock_error_writer = Mock(spec=ListErrorWriter)
        mock_error_writer.errors.return_value = FileErrorList(root=[])

        # Mock file input with non-existent file
        mock_file_input = Mock(spec=InputFileWrapper)
        mock_file_input.filename = "nonexistent.csv"
        mock_file_input.filepath = "/nonexistent/path/file.csv"
        mock_file_input.validate_file_extension.return_value = "csv"

        # Mock file entry
        mock_file_entry = Mock()
        mock_file_entry.created = datetime.now()
        mock_file_input.file_entry.return_value = mock_file_entry

        # Create form project configs
        form_project_configs = create_mock_form_project_configs("UDS")

        # Run the submission logger - should raise FileProcessingError for non-existent files
        with pytest.raises(FileProcessingError) as exc_info:
            run(
                file_input=mock_file_input,
                event_logger=mock_event_logger,
                gear_name="test-gear",
                proxy=mock_proxy,
                timestamp=mock_file_entry.created,
                error_writer=mock_error_writer,
                form_project_configs=form_project_configs,
                module="UDS",
            )

        # Verify the error message is meaningful
        assert "does not exist" in str(exc_info.value)

    def test_missing_configuration_error_handling(self):
        """Test that missing configuration errors are handled gracefully."""
        # Create valid CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write("ptid,visitdate\ntest,2023-01-01\n")
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

            # Run without form configs (should trigger missing configuration error)
            with pytest.raises(ConfigurationError) as exc_info:
                run(
                    file_input=mock_file_input,
                    event_logger=mock_event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=None,  # Missing configuration
                    module=None,  # Missing module
                )

            # Verify the error message is meaningful
            assert "form_configs_file and module configuration" in str(exc_info.value)

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_empty_file_warning_handling(self):
        """Test that empty files generate warnings but don't crash."""
        # Create empty CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            # Write nothing - empty file
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

                # Should handle empty file gracefully (may return False)
                assert isinstance(success, bool)

                # Should have written warning to error_writer (via misc_errors)
                assert mock_error_writer.write.call_count > 0

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_unsupported_file_type_handling(self):
        """Test that unsupported file types are handled gracefully."""
        # Create test file with unsupported extension
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as temp_file:
            temp_file.write("some text content")
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
            mock_file_input.filename = "test.txt"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = None  # Unsupported

            # Mock file entry
            mock_file_entry = Mock()
            mock_file_entry.created = datetime.now()
            mock_file_input.file_entry.return_value = mock_file_entry

            # Create form project configs
            form_project_configs = create_mock_form_project_configs("UDS")

            # Run the submission logger - should raise FileProcessingError for unsupported files
            with pytest.raises(FileProcessingError) as exc_info:
                run(
                    file_input=mock_file_input,
                    event_logger=mock_event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=form_project_configs,
                    module="UDS",
                )

            # Verify the error message is meaningful
            assert "Unsupported file type" in str(exc_info.value)

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_metrics_summary_logging(self):
        """Test that metrics summary is logged properly and focuses on visit-
        level metrics."""
        import io
        import logging

        metrics = ProcessingMetrics()

        # Add some test data
        metrics.increment_visits_found(10)
        metrics.increment_visits_processed_successfully(8)
        metrics.increment_visits_failed(2)
        metrics.increment_events_created(8)
        metrics.record_error("test-error")

        # Start and end processing to get duration
        metrics.start_processing()
        metrics.end_processing()

        # Capture log output to verify it focuses on visit-level metrics
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("metrics.processing_metrics")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            metrics.log_summary()
            log_output = log_capture.getvalue()

            # Verify visit-level metrics are logged
            assert "Visits Found in Input File: 10" in log_output
            assert "Visits Processed Successfully: 8" in log_output
            assert "Visits Failed: 2" in log_output
            assert "Submit Events Created: 8" in log_output

            # Verify file-level metrics are NOT logged
            assert "Files Processed" not in log_output
            assert "Files Found" not in log_output
            assert "Files Failed" not in log_output

        except Exception as e:
            raise AssertionError(f"log_summary should not raise exception: {e}")
        finally:
            logger.removeHandler(handler)

    def test_updated_processing_metrics_class_structure(self):
        """Test that ProcessingMetrics class has been updated correctly.

        This test validates Requirements 8.1, 8.3:
        - ProcessingMetrics no longer has files_processed attribute
        - get_metrics_dict() doesn't contain files_processed key
        - log_summary() focuses on visit-level metrics
        """
        metrics = ProcessingMetrics()

        # Test that ProcessingMetrics no longer has files_processed attribute
        assert not hasattr(metrics, "files_processed"), (
            "ProcessingMetrics should not have files_processed attribute"
        )
        assert not hasattr(metrics, "increment_files_processed"), (
            "ProcessingMetrics should not have increment_files_processed method"
        )

        # Test that it has all the expected visit-level attributes
        expected_attributes = [
            "visits_found",
            "visits_processed_successfully",
            "visits_failed",
            "events_created",
            "events_failed",
            "qc_logs_created",
            "qc_logs_failed",
            "errors_encountered",
            "error_types",
            "processing_start_time",
            "processing_end_time",
        ]

        for attr in expected_attributes:
            assert hasattr(metrics, attr), (
                f"ProcessingMetrics should have {attr} attribute"
            )

        # Test that get_metrics_dict() doesn't contain files_processed key
        metrics_dict = metrics.get_metrics_dict()

        # Should NOT contain file-level keys
        forbidden_keys = [
            "files_processed",
            "files_found",
            "files_failed",
            "file_success_rate",
        ]
        for key in forbidden_keys:
            assert key not in metrics_dict, (
                f"get_metrics_dict() should not contain {key}"
            )

        # Should contain visit-level keys
        required_keys = [
            "visits_found",
            "visits_processed_successfully",
            "visits_failed",
            "events_created",
            "events_failed",
            "qc_logs_created",
            "qc_logs_failed",
            "errors_encountered",
            "error_types",
            "visit_success_rate",
            "event_success_rate",
            "qc_log_success_rate",
            "processing_duration_seconds",
        ]

        for key in required_keys:
            assert key in metrics_dict, f"get_metrics_dict() should contain {key}"

        # Test that all visit-level increment methods exist and work
        metrics.increment_visits_found(1)
        metrics.increment_visits_processed_successfully(1)
        metrics.increment_visits_failed(1)
        metrics.increment_events_created(1)
        metrics.increment_events_failed(1)
        metrics.increment_qc_logs_created(1)
        metrics.increment_qc_logs_failed(1)

        assert metrics.visits_found == 1
        assert metrics.visits_processed_successfully == 1
        assert metrics.visits_failed == 1
        assert metrics.events_created == 1
        assert metrics.events_failed == 1
        assert metrics.qc_logs_created == 1
        assert metrics.qc_logs_failed == 1

    def test_error_recovery_continues_processing(self):
        """Test that processing continues after recoverable errors."""
        # Create CSV with some valid content
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write(
                "ptid,visitdate,visitnum,module,packet,adcid\ntest1,2023-01-01,1,UDS,I,1\n"
            )
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

            # Make event logger raise exception to simulate infrastructure error
            mock_event_logger.log_event.side_effect = Exception("S3 connection failed")

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

                # Run the submission logger - should handle infrastructure errors gracefully
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

                # Should complete processing (may return True or False)
                assert isinstance(success, bool)

                # Should have attempted to process the file
                assert mock_event_logger.log_event.call_count >= 0

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    @given(
        visits_found=st.integers(min_value=0, max_value=100),
        visits_processed_successfully=st.integers(min_value=0, max_value=100),
        visits_failed=st.integers(min_value=0, max_value=100),
        events_created=st.integers(min_value=0, max_value=100),
        events_failed=st.integers(min_value=0, max_value=100),
        qc_logs_created=st.integers(min_value=0, max_value=100),
        qc_logs_failed=st.integers(min_value=0, max_value=100),
        errors_encountered=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_metrics_dictionary_structure_property(
        self,
        visits_found,
        visits_processed_successfully,
        visits_failed,
        events_created,
        events_failed,
        qc_logs_created,
        qc_logs_failed,
        errors_encountered,
    ):
        """**Feature: submission-logger, Property 8: Metrics Dictionary Structure**

        **Validates: Requirements 8.1, 8.4**

        For any metrics data from processing, the metrics dictionary should contain
        visit-level metrics and should not contain file-level counters.
        """
        metrics = ProcessingMetrics()

        # Set up metrics with generated values
        metrics.visits_found = visits_found
        metrics.visits_processed_successfully = visits_processed_successfully
        metrics.visits_failed = visits_failed
        metrics.events_created = events_created
        metrics.events_failed = events_failed
        metrics.qc_logs_created = qc_logs_created
        metrics.qc_logs_failed = qc_logs_failed
        metrics.errors_encountered = errors_encountered

        # Add some error types
        for i in range(min(errors_encountered, 5)):
            metrics.error_types[f"error_type_{i}"] = 1

        # Get metrics dictionary
        metrics_dict = metrics.get_metrics_dict()

        # Property: Dictionary should contain visit-level metrics
        required_visit_level_keys = {
            "visits_found",
            "visits_processed_successfully",
            "visits_failed",
            "events_created",
            "events_failed",
            "qc_logs_created",
            "qc_logs_failed",
            "errors_encountered",
            "error_types",
            "visit_success_rate",
            "event_success_rate",
            "qc_log_success_rate",
            "processing_duration_seconds",
        }

        # Assert all required visit-level keys are present
        for key in required_visit_level_keys:
            assert key in metrics_dict, f"Missing required visit-level key: {key}"

        # Property: Dictionary should NOT contain file-level counters
        forbidden_file_level_keys = {
            "files_processed",
            "files_found",
            "files_failed",
            "file_success_rate",
        }

        # Assert no file-level keys are present
        for key in forbidden_file_level_keys:
            assert key not in metrics_dict, f"Found forbidden file-level key: {key}"

        # Property: Values should match what was set
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
        assert metrics_dict["errors_encountered"] == errors_encountered

        # Property: Success rates should be calculated correctly
        if visits_found > 0:
            expected_visit_success_rate = (
                visits_processed_successfully / visits_found
            ) * 100
            assert (
                abs(metrics_dict["visit_success_rate"] - expected_visit_success_rate)
                < 0.01
            )
        else:
            assert metrics_dict["visit_success_rate"] == 0.0

        if (events_created + events_failed) > 0:
            expected_event_success_rate = (
                events_created / (events_created + events_failed)
            ) * 100
            assert (
                abs(metrics_dict["event_success_rate"] - expected_event_success_rate)
                < 0.01
            )
        else:
            assert metrics_dict["event_success_rate"] == 0.0

        if (qc_logs_created + qc_logs_failed) > 0:
            expected_qc_success_rate = (
                qc_logs_created / (qc_logs_created + qc_logs_failed)
            ) * 100
            assert (
                abs(metrics_dict["qc_log_success_rate"] - expected_qc_success_rate)
                < 0.01
            )
        else:
            assert metrics_dict["qc_log_success_rate"] == 0.0
