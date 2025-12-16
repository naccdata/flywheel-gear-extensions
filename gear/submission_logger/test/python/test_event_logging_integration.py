"""Unit tests for event logging integration in submission logger."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.event_logger import VisitEventLogger
from event_logging.visit_events import VisitEvent
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from nacc_common.error_models import FileErrorList
from outputs.error_writer import ListErrorWriter
from s3.s3_bucket import S3BucketInterface
from submission_logger_app.main import run
from submission_logger_app.run import SubmissionLoggerVisitor


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


class TestEventLoggingIntegration:
    """Unit tests for event logging integration."""

    def test_visit_event_logger_configuration(self):
        """Test VisitEventLogger configuration with S3 bucket."""
        # Mock S3 bucket interface
        mock_s3_bucket = Mock(spec=S3BucketInterface)

        # Create VisitEventLogger
        event_logger = VisitEventLogger(s3_bucket=mock_s3_bucket, environment="test")

        # Verify configuration by testing behavior instead of private members
        # Create a test event to verify the logger is properly configured
        test_event = VisitEvent(
            action="submit",
            pipeline_adcid=42,
            project_label="test-project",
            center_label="test-center",
            gear_name="test-gear",
            ptid="TEST001",
            visit_date="2024-06-15",
            visit_number="1",
            datatype="form",
            module="UDS",
            packet="I",
            timestamp=datetime(2024, 6, 15, 14, 30, 45),
        )

        # Test that log_event calls the S3 bucket (verifies S3 integration)
        event_logger.log_event(test_event)
        mock_s3_bucket.put_file_object.assert_called_once()

        # Test that environment is used in filename generation
        filename = event_logger.create_event_filename(test_event)
        assert filename.startswith("test/")

    def test_event_filename_generation(self):
        """Test event filename generation follows established conventions."""
        # Mock S3 bucket interface
        mock_s3_bucket = Mock(spec=S3BucketInterface)

        # Create VisitEventLogger
        event_logger = VisitEventLogger(s3_bucket=mock_s3_bucket, environment="prod")

        # Create test event
        test_event = VisitEvent(
            action="submit",
            pipeline_adcid=42,
            project_label="test-project",
            center_label="test-center",
            gear_name="submission-logger",
            ptid="TEST001",
            visit_date="2024-06-15",
            visit_number="1",
            datatype="form",
            module="UDS",
            packet="I",
            timestamp=datetime(2024, 6, 15, 14, 30, 45),
        )

        # Generate filename
        filename = event_logger.create_event_filename(test_event)

        # Verify filename format:
        # {env}/log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
        expected_filename = (
            "prod/log-submit-20240615-143045-42-test-project-TEST001-1.json"
        )
        assert filename == expected_filename

    def test_event_filename_with_special_characters(self):
        """Test event filename generation handles special characters in project
        labels."""
        # Mock S3 bucket interface
        mock_s3_bucket = Mock(spec=S3BucketInterface)

        # Create VisitEventLogger
        event_logger = VisitEventLogger(s3_bucket=mock_s3_bucket, environment="dev")

        # Create test event with special characters in project label
        test_event = VisitEvent(
            action="submit",
            pipeline_adcid=42,
            project_label="test/project\\with-special",
            center_label="test-center",
            gear_name="submission-logger",
            ptid="TEST001",
            visit_date="2024-06-15",
            visit_number="1",
            datatype="form",
            module="UDS",
            packet="I",
            timestamp=datetime(2024, 6, 15, 14, 30, 45),
        )

        # Generate filename
        filename = event_logger.create_event_filename(test_event)

        # Verify special characters are replaced with hyphens
        expected_filename = (
            "dev/log-submit-20240615-143045-42-test-project-with-special-TEST001-1.json"
        )
        assert filename == expected_filename

    def test_s3_bucket_creation_success(self):
        """Test successful S3 bucket creation in SubmissionLoggerVisitor."""
        # Mock context and parameter store
        mock_context = Mock(spec=GearToolkitContext)
        mock_manifest = Mock()
        mock_manifest.get.return_value = "submission-logger"
        mock_context.manifest = mock_manifest

        mock_config = Mock()
        mock_config.get.side_effect = lambda key, default: {
            "environment": "test",
            "event_bucket": "test-bucket",
        }.get(key, default)
        mock_context.config = mock_config

        mock_parameter_store = Mock()

        # Mock S3BucketInterface creation
        mock_s3_bucket = Mock(spec=S3BucketInterface)

        with (
            patch(
                "submission_logger_app.run.GearBotClient.create"
            ) as mock_client_create,
            patch(
                "submission_logger_app.run.InputFileWrapper.create"
            ) as mock_file_create,
            patch(
                "submission_logger_app.run.S3BucketInterface.create_from_environment"
            ) as mock_s3_create,
        ):
            mock_client_create.return_value = Mock()
            mock_file_create.return_value = Mock()
            mock_s3_create.return_value = mock_s3_bucket

            # Create SubmissionLoggerVisitor
            visitor = SubmissionLoggerVisitor.create(
                context=mock_context, parameter_store=mock_parameter_store
            )

            # Verify S3 bucket was created with correct parameters
            mock_s3_create.assert_called_once_with("test-bucket")

            # Verify VisitEventLogger was created successfully
            # We can't access private members, so we verify creation succeeded
            assert visitor is not None

    def test_s3_bucket_creation_failure(self):
        """Test S3 bucket creation failure raises GearExecutionError."""
        # Mock context and parameter store
        mock_context = Mock(spec=GearToolkitContext)
        mock_manifest = Mock()
        mock_manifest.get.return_value = "submission-logger"
        mock_context.manifest = mock_manifest

        mock_config = Mock()
        mock_config.get.side_effect = lambda key, default: {
            "environment": "test",
            "event_bucket": "invalid-bucket",
        }.get(key, default)
        mock_context.config = mock_config

        mock_parameter_store = Mock()

        with (
            patch(
                "submission_logger_app.run.GearBotClient.create"
            ) as mock_client_create,
            patch(
                "submission_logger_app.run.InputFileWrapper.create"
            ) as mock_file_create,
            patch(
                "submission_logger_app.run.S3BucketInterface.create_from_environment"
            ) as mock_s3_create,
        ):
            mock_client_create.return_value = Mock()
            mock_file_create.return_value = Mock()
            mock_s3_create.return_value = None  # Simulate S3 bucket creation failure

            # Verify GearExecutionError is raised
            with pytest.raises(
                GearExecutionError, match="Unable to access S3 bucket invalid-bucket"
            ):
                SubmissionLoggerVisitor.create(
                    context=mock_context, parameter_store=mock_parameter_store
                )

    def test_event_storage_integration(self):
        """Test event storage integration with S3."""
        # Create test CSV data
        csv_content = (
            "ptid,visitdate,visitnum,module,packet,adcid\nTEST001,2024-06-15,1,UDS,I,42"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write(csv_content)
            temp_file_path = temp_file.name

        try:
            # Mock S3 bucket interface
            mock_s3_bucket = Mock(spec=S3BucketInterface)

            # Create real VisitEventLogger with mock S3 bucket
            event_logger = VisitEventLogger(
                s3_bucket=mock_s3_bucket, environment="test"
            )

            # Mock other dependencies
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with timestamp
            mock_file_entry = Mock()
            mock_file_entry.created = datetime(2024, 6, 15, 14, 30, 45)
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

                # Run the submission logger
                success = run(
                    file_input=mock_file_input,
                    event_logger=event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=form_project_configs,
                    module="UDS",
                )

                # Verify success
                assert success, "Processing should succeed"

                # Verify S3 put_file_object was called
                assert mock_s3_bucket.put_file_object.call_count == 1

                # Get the call arguments
                call_args = mock_s3_bucket.put_file_object.call_args
                filename = call_args[1]["filename"]
                contents = call_args[1]["contents"]

                # Verify filename format
                assert filename.startswith("test/log-submit-")
                assert filename.endswith("-42-test-project-TEST001-1.json")

                # Verify contents is valid JSON
                import json

                event_data = json.loads(contents)
                assert event_data["action"] == "submit"
                assert event_data["ptid"] == "TEST001"
                assert event_data["visit_date"] == "2024-06-15"
                assert event_data["module"] == "UDS"

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)

    def test_multiple_events_storage(self):
        """Test storage of multiple events from CSV with multiple visits."""
        # Create CSV with multiple visits
        csv_content = (
            "ptid,visitdate,visitnum,module,packet,adcid\n"
            "TEST001,2024-06-15,1,UDS,I,42\n"
            "TEST002,2024-06-16,2,FTLD,F,43\n"
            "TEST003,2024-06-17,1,LBD,I,44"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_file:
            temp_file.write(csv_content)
            temp_file_path = temp_file.name

        try:
            # Mock S3 bucket interface
            mock_s3_bucket = Mock(spec=S3BucketInterface)

            # Create real VisitEventLogger with mock S3 bucket
            event_logger = VisitEventLogger(
                s3_bucket=mock_s3_bucket, environment="test"
            )

            # Mock other dependencies
            mock_proxy = Mock(spec=FlywheelProxy)
            mock_context = Mock(spec=GearToolkitContext)
            mock_error_writer = Mock(spec=ListErrorWriter)
            mock_error_writer.errors.return_value = FileErrorList(root=[])

            # Mock file input
            mock_file_input = Mock(spec=InputFileWrapper)
            mock_file_input.filename = "test.csv"
            mock_file_input.filepath = temp_file_path
            mock_file_input.validate_file_extension.return_value = "csv"

            # Mock file entry with timestamp
            mock_file_entry = Mock()
            mock_file_entry.created = datetime(2024, 6, 15, 14, 30, 45)
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

                # Create form project configs that accepts all modules
                form_project_configs = FormProjectConfigs(
                    primary_key="ptid",
                    accepted_modules=["UDS", "FTLD", "LBD"],
                    module_configs={
                        "UDS": create_mock_module_configs(),
                        "FTLD": create_mock_module_configs(),
                        "LBD": create_mock_module_configs(),
                    },
                )

                # Run the submission logger with UDS module (first visit's module)
                success = run(
                    file_input=mock_file_input,
                    event_logger=event_logger,
                    gear_name="test-gear",
                    proxy=mock_proxy,
                    timestamp=mock_file_entry.created,
                    error_writer=mock_error_writer,
                    form_project_configs=form_project_configs,
                    module="UDS",  # This will process all visits but use UDS config
                )

                # Verify success
                assert success, "Processing should succeed"

                # Verify multiple S3 put_file_object calls (one per visit)
                assert mock_s3_bucket.put_file_object.call_count == 3

                # Verify all calls have different filenames (different PTIDs)
                call_args_list = mock_s3_bucket.put_file_object.call_args_list
                filenames = [call[1]["filename"] for call in call_args_list]

                # All filenames should be unique
                assert len(set(filenames)) == 3

                # All should be submit events
                for call_args in call_args_list:
                    filename = call_args[1]["filename"]
                    assert "log-submit-" in filename

        finally:
            # Clean up temporary file
            Path(temp_file_path).unlink(missing_ok=True)
