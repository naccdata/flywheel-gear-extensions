"""Unit tests for event capture config initialization and duplicate event
capture behavior.

Tests cover:
- Four config states for event capture initialization
  (both, only bucket, only env, neither)
- S3 error raises GearExecutionError
- Missing date field in row skips event capture (logs warning, doesn't raise)
- Metadata copy failure does not trigger second event capture

Requirements: 3.2, 3.3, 3.4, 5.4, 2.7, 6.3
"""

import logging
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
from form_csv_app.run import initialize_event_capture
from gear_execution.gear_execution import GearExecutionError
from s3.s3_bucket import S3InterfaceError

# ============================================================================
# Tests: Config state handling (Requirements 3.2, 3.3, 3.4, 5.4)
# ============================================================================


class TestConfigStateHandling:
    """Test initialize_event_capture with the four config states."""

    @patch("form_csv_app.run.S3BucketInterface.create_from_environment")
    def test_both_config_values_present_creates_event_capture(self, mock_s3):
        """When both event_bucket and event_environment are provided,
        VisitEventCapture should be created.

        Requirement 3.2: Both provided -> create VisitEventCapture
        """
        mock_s3.return_value = Mock()

        result = initialize_event_capture(
            event_bucket="my-bucket",
            event_environment="prod",
        )

        mock_s3.assert_called_once_with("my-bucket")
        assert result is not None
        assert isinstance(result, VisitEventCapture)

    def test_only_bucket_provided_disables_event_capture(self, caplog):
        """When only event_bucket is provided, event_capture should be None and
        a warning logged.

        Requirement 5.4: Only one provided -> skip, log warning
        """
        with caplog.at_level(logging.WARNING):
            result = initialize_event_capture(
                event_bucket="my-bucket",
                event_environment="",
            )

        assert result is None
        assert any("Both event_bucket" in r.message for r in caplog.records)

    def test_only_environment_provided_disables_event_capture(self, caplog):
        """When only event_environment is provided, event_capture should be
        None and a warning logged.

        Requirement 5.4: Only one provided -> skip, log warning
        """
        with caplog.at_level(logging.WARNING):
            result = initialize_event_capture(
                event_bucket="",
                event_environment="prod",
            )

        assert result is None
        assert any("Both event_bucket" in r.message for r in caplog.records)

    def test_neither_config_value_provided_disables_silently(self, caplog):
        """When neither event_bucket nor event_environment are provided,
        event_capture should be None with no warning.

        Requirement 3.4: Neither provided -> None, no error
        """
        with caplog.at_level(logging.WARNING):
            result = initialize_event_capture(
                event_bucket="",
                event_environment="",
            )

        assert result is None
        assert not any("event_bucket" in r.message for r in caplog.records)

    @patch("form_csv_app.run.S3BucketInterface.create_from_environment")
    def test_s3_error_raises_gear_execution_error(self, mock_s3):
        """When S3BucketInterface.create_from_environment raises, a
        GearExecutionError should be raised.

        Requirement 3.3: S3InterfaceError -> GearExecutionError
        """
        mock_s3.side_effect = S3InterfaceError("Bucket not found")

        with pytest.raises(GearExecutionError, match="Unable to access S3 bucket"):
            initialize_event_capture(
                event_bucket="bad-bucket",
                event_environment="prod",
            )


# ============================================================================
# Tests: __capture_duplicate_event edge cases (Requirements 2.7, 6.3)
# ============================================================================


class TestCaptureDuplicateEventEdgeCases:
    """Test __capture_duplicate_event behavior through visit_row()."""

    def test_invalid_date_field_skips_event_capture(
        self, caplog, create_valid_row, create_visitor_with_mocks
    ):
        """When the date field has an invalid format that can't be parsed by
        DataIdentification.from_form_record, __capture_duplicate_event should
        log a warning and skip, not raise.

        Requirement 2.7: DataIdentification can't be constructed ->
        skip, log
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=True,
        )

        # Provide a date value that exists (passes required_fields check)
        # but cannot be parsed by DataIdentification.from_form_record
        row = create_valid_row(visitdate="not-a-valid-date")

        with caplog.at_level(logging.WARNING):
            result = visitor.visit_row(row, line_num=1)

        # visit_row should still return True (duplicate detected and processed)
        assert result is True
        # capture_event should NOT have been called (skipped due to bad date)
        mock_event_capture.capture_event.assert_not_called()
        # Warning should be logged about DataIdentification failure
        assert any("Cannot construct" in r.message for r in caplog.records)

    def test_empty_date_field_skips_event_capture(
        self, caplog, create_valid_row, create_visitor_with_mocks
    ):
        """When the date field is empty string, event capture is skipped.

        Requirement 2.7: DataIdentification can't be constructed -> skip
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=True,
        )

        # Empty date passes None check but will raise EmptyFieldError
        # when DataIdentification.from_form_record tries to parse it
        row = create_valid_row(visitdate="")

        with caplog.at_level(logging.WARNING):
            result = visitor.visit_row(row, line_num=1)

        # visit_row should still return True
        assert result is True
        mock_event_capture.capture_event.assert_not_called()

    def test_no_event_capture_configured_skips_silently(
        self, create_valid_row, create_visitor_with_mocks
    ):
        """When event_capture is None, no event is captured and no error
        occurs.

        Requirement 3.4: No event capture configured -> no events
        """
        visitor, _ = create_visitor_with_mocks(
            event_capture=None,
            timestamp=datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc),
            is_existing_visit=True,
        )

        row = create_valid_row()
        result = visitor.visit_row(row, line_num=1)

        assert result is True

    def test_no_timestamp_configured_skips_silently(
        self, create_valid_row, create_visitor_with_mocks
    ):
        """When timestamp is None, __capture_duplicate_event returns early."""
        mock_event_capture = Mock(spec=VisitEventCapture)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=None,
            is_existing_visit=True,
        )

        row = create_valid_row()
        result = visitor.visit_row(row, line_num=1)

        assert result is True
        mock_event_capture.capture_event.assert_not_called()

    def test_capture_event_failure_does_not_interrupt_processing(
        self, caplog, create_valid_row, create_visitor_with_mocks
    ):
        """When capture_event raises an exception, visit_row still returns True
        and the row is still added to __existing_visits.

        Requirement 7.1, 7.2, 7.3: Event capture failure -> continue
        processing
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        mock_event_capture.capture_event.side_effect = RuntimeError("S3 failure")
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=True,
        )

        row = create_valid_row()
        with caplog.at_level(logging.WARNING):
            result = visitor.visit_row(row, line_num=1)

        # Processing continues despite capture failure
        assert result is True
        # capture_event was called (it just failed)
        mock_event_capture.capture_event.assert_called_once()
        # Warning should have been logged
        assert any("Failed to capture" in r.message for r in caplog.records)

    def test_metadata_copy_failure_does_not_trigger_second_event(
        self, create_valid_row, create_visitor_with_mocks
    ):
        """When metadata copy fails for a duplicate visit, causing re-addition
        to the current batch, no second duplicate-submit event is captured.

        Requirement 6.3: Only one event at detection point, not during
        batch reprocessing.
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=True,
        )

        row = create_valid_row()
        result = visitor.visit_row(row, line_num=1)
        assert result is True

        # At this point, capture_event was called once during visit_row
        assert mock_event_capture.capture_event.call_count == 1

        # Now call update_existing_visits_error_log which simulates what
        # happens when metadata copy fails (re-adds to current_batch).
        # The key: no second event is captured during this reprocessing.
        visitor.update_existing_visits_error_log(downstream_gears=["form-qc-checker"])

        # Still only one capture_event call
        assert mock_event_capture.capture_event.call_count == 1

    def test_duplicate_event_captured_on_valid_row(
        self, create_valid_row, create_visitor_with_mocks
    ):
        """When a valid duplicate row is detected, exactly one event is
        captured with correct fields.

        Requirement 2.1: is_existing_visit True -> capture event
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=True,
        )

        row = create_valid_row()
        result = visitor.visit_row(row, line_num=1)

        assert result is True
        mock_event_capture.capture_event.assert_called_once()

        # Verify the event has correct action and fields
        captured_event = mock_event_capture.capture_event.call_args[0][0]
        assert captured_event.action == "duplicate-submit"
        assert captured_event.datatype == "form"
        assert captured_event.gear_name == "form-transformer"
        assert captured_event.project_label == "ingest-form"
        assert captured_event.center_label == "adrc42"
        assert captured_event.timestamp == timestamp

    def test_non_duplicate_row_does_not_trigger_event(
        self, create_valid_row, create_visitor_with_mocks
    ):
        """When is_existing_visit returns False, no event is captured.

        Requirement 6.2: Non-duplicates -> no events
        """
        mock_event_capture = Mock(spec=VisitEventCapture)
        timestamp = datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc)

        visitor, _ = create_visitor_with_mocks(
            event_capture=mock_event_capture,
            timestamp=timestamp,
            is_existing_visit=False,
        )

        row = create_valid_row()
        result = visitor.visit_row(row, line_num=1)

        assert result is True
        mock_event_capture.capture_event.assert_not_called()
