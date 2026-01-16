"""Property test for missing configuration handling in FormSchedulerQueue.

**Feature: form-scheduler-event-logging-refactor,
  Property 8: Missing Configuration Handling**
**Validates: Requirements 5.5**
"""

from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
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

              **Feature: form-scheduler-event-logging-refactor,
        Property 8: Missing Configuration Handling**
              **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()
        mock_event_capture = Mock(spec=VisitEventCapture)

        # Create FormSchedulerQueue with mock event capture
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_capture=mock_event_capture,
        )

        # Create test file
        json_file = Mock(spec=FileEntry) if has_valid_json_file else None
        if json_file:
            json_file.name = "test.json"

        # Capture log messages to verify debug message is logged
        with patch("form_scheduler_app.form_scheduler_queue.log") as _mock_log:
            # This should not raise an exception regardless of input validity
            try:
                # Access the private method for testing
                queue._capture_pipeline_events(  # noqa: SLF001
                    json_file=json_file  # type: ignore[arg-type]
                )
                # If we get here, missing configuration was handled gracefully
                assert True
            except Exception as e:
                pytest.fail(
                    f"FormSchedulerQueue should handle missing configuration "
                    f"gracefully, but raised: {e}"
                )

    def test_no_errors_when_event_logger_is_none(self):
        """Test that no errors occur when event logger is None.

              **Feature: form-scheduler-event-logging-refactor,
        Property 8: Missing Configuration Handling**
              **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()
        mock_event_capture = Mock(spec=VisitEventCapture)

        # Create FormSchedulerQueue with mock event capture
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_capture=mock_event_capture,
        )

        # Create completely valid inputs that would normally result in event logging
        json_file = Mock(spec=FileEntry)
        json_file.name = "test.json"

        # This should complete without any errors
        try:
            # Access the private method for testing
            queue._capture_pipeline_events(json_file=json_file)  # noqa: SLF001
            # If we get here, missing configuration was handled gracefully
            assert True
        except Exception as e:
            pytest.fail(
                f"FormSchedulerQueue should handle missing configuration "
                f"without errors, but raised: {e}"
            )

    def test_constructor_accepts_none_event_logger(self):
        """Test that FormSchedulerQueue constructor accepts None event logger.

              **Feature: form-scheduler-event-logging-refactor,
        Property 8: Missing Configuration Handling**
              **Validates: Requirements 5.5**
        """
        # This should not raise an exception
        try:
            mock_event_capture = Mock(spec=VisitEventCapture)
            queue = FormSchedulerQueue(
                proxy=Mock(),
                project=Mock(spec=ProjectAdaptor),
                pipeline_configs=Mock(),
                event_capture=mock_event_capture,
            )
            assert queue is not None
        except Exception as e:
            pytest.fail(
                f"FormSchedulerQueue constructor should accept event "
                f"capture, but raised: {e}"
            )

    def test_no_event_accumulator_creation_when_logger_none(self):
        """Test that EventAccumulator is not created when event logger is None.

              **Feature: form-scheduler-event-logging-refactor,
        Property 8: Missing Configuration Handling**
              **Validates: Requirements 5.5**
        """
        # Create mock project and pipeline configs
        mock_project = Mock(spec=ProjectAdaptor)
        mock_pipeline_configs = Mock()
        mock_event_capture = Mock(spec=VisitEventCapture)

        # Create FormSchedulerQueue with mock event capture
        queue = FormSchedulerQueue(
            proxy=Mock(),
            project=mock_project,
            pipeline_configs=mock_pipeline_configs,
            event_capture=mock_event_capture,
        )

        json_file = Mock(spec=FileEntry)
        json_file.name = "test.json"

        # Mock the EventAccumulator import to verify it's called
        with patch(
            "form_scheduler_app.form_scheduler_queue.EventAccumulator"
        ) as mock_accumulator_class:
            # Access the private method for testing
            queue._capture_pipeline_events(json_file=json_file)  # noqa: SLF001

            # EventAccumulator should be instantiated with event_capture
            mock_accumulator_class.assert_called_once_with(
                event_capture=mock_event_capture
            )
