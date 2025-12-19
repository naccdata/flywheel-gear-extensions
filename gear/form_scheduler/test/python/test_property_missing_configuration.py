"""Property test for missing configuration handling in FormSchedulerQueue.

**Feature: form-scheduler-event-logging-refactor, Property 8: Missing Configuration Handling**
**Validates: Requirements 5.5**
"""

from unittest.mock import Mock, patch

import pytest
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from form_scheduler_app.form_scheduler_queue import FormSchedulerQueue
from hypothesis import given
from hypothesis import strategies as st


class TestMissingConfigurationHandling:
    """Test that FormSchedulerQueue handles missing event logger configuration
    gracefully."""

    @given(
        has_valid_json_file=st.booleans(),
    )
    def test_skip_event_logging_when_event_logger_not_configured(
        self, has_valid_json_file
    ):
        """Test that event logging is skipped entirely when event logger is
        None.

        **Feature: form-scheduler-event-logging-refactor, Property 8: Missing Configuration Handling**
        **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()

        # Create FormSchedulerQueue with None event logger (not configured)
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_logger=None,  # Not configured
        )

        # Create test file
        json_file = Mock(spec=FileEntry) if has_valid_json_file else None
        if json_file:
            json_file.name = "test.json"

        # Create mock pipeline
        mock_pipeline = Mock()
        mock_pipeline.name = "test_pipeline"

        # Capture log messages to verify debug message is logged
        with patch("form_scheduler_app.form_scheduler_queue.log") as mock_log:
            # This should not raise an exception regardless of input validity
            try:
                queue._log_pipeline_events(file=json_file, pipeline=mock_pipeline)  # type: ignore[arg-type]
                # If we get here, missing configuration was handled gracefully
                assert True
            except Exception as e:
                pytest.fail(
                    f"FormSchedulerQueue should handle missing configuration gracefully, but raised: {e}"
                )

            # Should have logged debug message about missing configuration
            mock_log.debug.assert_called_with(
                "Event logger not configured, skipping event logging"
            )

    def test_no_errors_when_event_logger_is_none(self):
        """Test that no errors occur when event logger is None.

        **Feature: form-scheduler-event-logging-refactor, Property 8: Missing Configuration Handling**
        **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()

        # Create FormSchedulerQueue with None event logger
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_logger=None,
        )

        # Create completely valid inputs that would normally result in event logging
        json_file = Mock(spec=FileEntry)
        json_file.name = "test.json"

        mock_pipeline = Mock()
        mock_pipeline.name = "test_pipeline"

        # This should complete without any errors
        try:
            queue._log_pipeline_events(file=json_file, pipeline=mock_pipeline)
            # If we get here, missing configuration was handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"FormSchedulerQueue should handle missing configuration without errors, but raised: {e}"
            )

    def test_constructor_accepts_none_event_logger(self):
        """Test that FormSchedulerQueue constructor accepts None event logger.

        **Feature: form-scheduler-event-logging-refactor, Property 8: Missing Configuration Handling**
        **Validates: Requirements 5.5**
        """
        # This should not raise an exception
        try:
            queue = FormSchedulerQueue(
                proxy=Mock(),
                project=Mock(spec=ProjectAdaptor),
                pipeline_configs=Mock(),
                event_logger=None,
            )
            assert queue is not None
        except Exception as e:
            pytest.fail(
                f"FormSchedulerQueue constructor should accept None event logger, but raised: {e}"
            )

    def test_no_event_accumulator_creation_when_logger_none(self):
        """Test that EventAccumulator is not created when event logger is None.

        **Feature: form-scheduler-event-logging-refactor, Property 8: Missing Configuration Handling**
        **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()

        # Create FormSchedulerQueue with None event logger
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_logger=None,
        )

        json_file = Mock(spec=FileEntry)
        json_file.name = "test.json"
        mock_pipeline = Mock()

        # Mock the EventAccumulator import to verify it's not called
        with patch(
            "form_scheduler_app.simplified_event_accumulator.EventAccumulator"
        ) as mock_accumulator_class:
            queue._log_pipeline_events(file=json_file, pipeline=mock_pipeline)

            # EventAccumulator should not be instantiated when event_logger is None
            mock_accumulator_class.assert_not_called()
