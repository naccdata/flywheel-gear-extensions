"""Unit tests for PipelineEventLoggerVisitor.create() configuration
validation."""

from unittest.mock import Mock, patch

import pytest
from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from pipeline_event_logger_app.run import PipelineEventLoggerVisitor


class TestPipelineEventLoggerVisitorCreate:
    """Tests for PipelineEventLoggerVisitor.create() factory method."""

    @patch("pipeline_event_logger_app.run.ContextClient.create")
    @patch("pipeline_event_logger_app.run.InputFileWrapper.create")
    def test_event_actions_without_environment_raises(
        self,
        mock_input_wrapper: Mock,
        mock_context_client: Mock,
    ) -> None:
        """Non-empty event_actions without event_environment raises error."""
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "upstream_gear_name": "test-gear",
            "event_actions": {"pass": "pass-qc"},
            "event_bucket": "test-bucket",
            # event_environment is missing
        }

        mock_context_client.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        with pytest.raises(GearExecutionError) as exc_info:
            PipelineEventLoggerVisitor.create(context)

        assert "event_environment" in str(exc_info.value)
        assert "event_bucket" in str(exc_info.value)

    @patch("pipeline_event_logger_app.run.ContextClient.create")
    @patch("pipeline_event_logger_app.run.InputFileWrapper.create")
    def test_event_actions_without_bucket_raises(
        self,
        mock_input_wrapper: Mock,
        mock_context_client: Mock,
    ) -> None:
        """Non-empty event_actions without event_bucket raises error."""
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "upstream_gear_name": "test-gear",
            "event_actions": {"pass": "pass-qc"},
            "event_environment": "prod",
            # event_bucket is missing
        }

        mock_context_client.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        with pytest.raises(GearExecutionError) as exc_info:
            PipelineEventLoggerVisitor.create(context)

        assert "event_environment" in str(exc_info.value)
        assert "event_bucket" in str(exc_info.value)

    @patch("pipeline_event_logger_app.run.S3BucketInterface.create_from_environment")
    @patch("pipeline_event_logger_app.run.ContextClient.create")
    @patch("pipeline_event_logger_app.run.InputFileWrapper.create")
    def test_empty_event_actions_results_in_no_capture(
        self,
        mock_input_wrapper: Mock,
        mock_context_client: Mock,
        mock_s3_bucket: Mock,
    ) -> None:
        """Empty event_actions does not initialize S3 or event capture."""
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "upstream_gear_name": "test-gear",
            "event_actions": {},
        }

        mock_context_client.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        visitor = PipelineEventLoggerVisitor.create(context)

        assert visitor is not None
        # S3 bucket should not have been initialized
        mock_s3_bucket.assert_not_called()

    @patch("pipeline_event_logger_app.run.S3BucketInterface.create_from_environment")
    @patch("pipeline_event_logger_app.run.ContextClient.create")
    @patch("pipeline_event_logger_app.run.InputFileWrapper.create")
    def test_none_event_actions_results_in_no_capture(
        self,
        mock_input_wrapper: Mock,
        mock_context_client: Mock,
        mock_s3_bucket: Mock,
    ) -> None:
        """None/missing event_actions defaults to empty dict, no capture."""
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "upstream_gear_name": "test-gear",
            # event_actions not provided
        }

        mock_context_client.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        visitor = PipelineEventLoggerVisitor.create(context)

        assert visitor is not None
        # S3 bucket should not have been initialized
        mock_s3_bucket.assert_not_called()

    @patch("pipeline_event_logger_app.run.S3BucketInterface.create_from_environment")
    @patch("pipeline_event_logger_app.run.ContextClient.create")
    @patch("pipeline_event_logger_app.run.InputFileWrapper.create")
    def test_valid_event_config_creates_capture(
        self,
        mock_input_wrapper: Mock,
        mock_context_client: Mock,
        mock_s3_bucket: Mock,
    ) -> None:
        """Valid event configuration initializes S3 and event capture."""
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "upstream_gear_name": "test-gear",
            "event_actions": {"pass": "pass-qc"},
            "event_environment": "prod",
            "event_bucket": "test-bucket",
        }

        mock_context_client.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)
        mock_s3_bucket.return_value = Mock()

        visitor = PipelineEventLoggerVisitor.create(context)

        assert visitor is not None
        mock_s3_bucket.assert_called_once_with("test-bucket")
