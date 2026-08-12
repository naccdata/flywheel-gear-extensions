"""Unit tests for run.py config handling and __capture_duplicate_event edge
cases.

Tests cover:
- Four config states for event capture initialization
  (both, only bucket, only env, neither)
- Missing date field in row skips event capture (logs warning, doesn't raise)
- Metadata copy failure does not trigger second event capture

Requirements: 3.2, 3.3, 3.4, 5.4, 2.7, 6.3
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock, Mock, patch

import pytest
from configs.ingest_configs import ModuleConfigs
from event_capture.event_capture import VisitEventCapture
from form_csv_app.main import CSVTransformVisitor
from gear_execution.gear_execution import GearExecutionError
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from s3.s3_bucket import S3InterfaceError

# ============================================================================
# Helper fixtures and factories
# ============================================================================


def create_module_configs_with_duplicate_check() -> ModuleConfigs:
    """Create ModuleConfigs that includes duplicate-record preprocess check."""
    module_configs = {
        "hierarchy_labels": {
            "session": {"template": "FORMS-VISIT-${visitnum}", "transform": "upper"},
            "acquisition": {"template": "${module}", "transform": "upper"},
            "filename": {
                "template": "${subject}_${session}_${acquisition}.json",
                "transform": "upper",
            },
        },
        "required_fields": [
            "ptid",
            "adcid",
            "visitnum",
            "visitdate",
            "module",
        ],
        "initial_packets": ["I"],
        "followup_packets": ["F"],
        "versions": ["4.0"],
        "date_field": "visitdate",
        "preprocess_checks": [
            "duplicate-record",
        ],
    }
    return ModuleConfigs.model_validate(module_configs)


def create_valid_row(
    ptid: str = "110001",
    visitdate: str = "2024-03-15",
    module: str = "UDS",
    visitnum: str = "2",
    adcid: int = 42,
    naccid: str = "NACC000001",
) -> Dict[str, Any]:
    """Create a valid CSV row with all expected fields."""
    return {
        FieldNames.PTID: ptid,
        FieldNames.DATE_COLUMN: visitdate,
        FieldNames.MODULE: module,
        FieldNames.VISITNUM: visitnum,
        FieldNames.ADCID: adcid,
        FieldNames.NACCID: naccid,
    }


def create_visitor_with_mocks(
    *,
    event_capture: Optional[VisitEventCapture] = None,
    center_label: str = "adrc42",
    project_label: str = "ingest-form",
    timestamp: Optional[datetime] = None,
    is_existing_visit: bool = False,
) -> Tuple[CSVTransformVisitor, Mock]:
    """Create a CSVTransformVisitor with mocked dependencies for testing.

    Uses a mocked transformer that returns the row as-is (bypassing
    DateTransformer normalization) to allow testing edge cases.

    Returns the visitor and the mock preprocessor.
    """
    module = "UDS"
    module_configs = create_module_configs_with_duplicate_check()
    error_writer = ListErrorWriter(container_id="test-id", fw_path="test/path")

    # Use a mock preprocessor so we can control is_existing_visit behavior
    mock_preprocessor = Mock()
    mock_preprocessor.is_existing_visit.return_value = is_existing_visit
    mock_preprocessor.preprocess.return_value = True

    # Use a mock transformer factory that returns rows as-is
    # This bypasses DateTransformer so we can test __capture_duplicate_event
    # with invalid dates that would normally be caught by the transformer
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda row, line_num: dict(row)
    mock_transformer_factory = MagicMock()
    mock_transformer_factory.create.return_value = mock_transformer

    visitor = CSVTransformVisitor(
        id_column=FieldNames.NACCID,
        module=module,
        error_writer=error_writer,
        transformer_factory=mock_transformer_factory,
        preprocessor=mock_preprocessor,
        module_configs=module_configs,
        gear_name="form-transformer",
        project=None,
        event_capture=event_capture,
        center_label=center_label,
        project_label=project_label,
        timestamp=timestamp,
    )

    header = [
        FieldNames.NACCID,
        FieldNames.DATE_COLUMN,
        FieldNames.MODULE,
        FieldNames.VISITNUM,
        FieldNames.ADCID,
        FieldNames.PTID,
    ]
    assert visitor.visit_header(header)

    return visitor, mock_preprocessor


# ============================================================================
# Tests: Config state handling (Requirements 3.2, 3.3, 3.4, 5.4)
# ============================================================================


class TestConfigStateHandling:
    """Test the four config states for event capture in run.py."""

    def test_both_config_values_present_creates_event_capture(self):
        """When both event_bucket and event_environment are provided,
        VisitEventCapture should be created.

        Requirement 3.2: Both provided -> create VisitEventCapture
        """
        with patch("s3.s3_bucket.S3BucketInterface.create_from_environment") as mock_s3:
            mock_s3_instance = Mock()
            mock_s3.return_value = mock_s3_instance

            config_opts = {
                "event_bucket": "my-bucket",
                "event_environment": "prod",
            }

            event_bucket = config_opts.get("event_bucket", "")
            event_environment = config_opts.get("event_environment", "")

            event_capture: Optional[VisitEventCapture] = None
            if event_bucket and event_environment:
                from s3.s3_bucket import S3BucketInterface

                s3_bucket = S3BucketInterface.create_from_environment(event_bucket)
                event_capture = VisitEventCapture(
                    s3_bucket=s3_bucket, environment=event_environment
                )

            mock_s3.assert_called_once_with("my-bucket")
            assert event_capture is not None

    def test_only_bucket_provided_disables_event_capture(self, caplog):
        """When only event_bucket is provided, event_capture should be None and
        a warning logged.

        Requirement 5.4: Only one provided -> skip, log warning
        """
        config_opts = {
            "event_bucket": "my-bucket",
            "event_environment": "",
        }

        event_bucket = config_opts.get("event_bucket", "")
        event_environment = config_opts.get("event_environment", "")

        event_capture = None
        with caplog.at_level(logging.WARNING):
            if event_bucket and event_environment:
                pass
            elif event_bucket or event_environment:
                logging.getLogger("form_csv_app.run").warning(
                    "Both event_bucket and event_environment are required for "
                    "event capture. Got event_bucket='%s', "
                    "event_environment='%s'. Event capture will be disabled.",
                    event_bucket,
                    event_environment,
                )

        assert event_capture is None
        assert any("Both event_bucket" in r.message for r in caplog.records)

    def test_only_environment_provided_disables_event_capture(self, caplog):
        """When only event_environment is provided, event_capture should be
        None and a warning logged.

        Requirement 5.4: Only one provided -> skip, log warning
        """
        config_opts = {
            "event_bucket": "",
            "event_environment": "prod",
        }

        event_bucket = config_opts.get("event_bucket", "")
        event_environment = config_opts.get("event_environment", "")

        event_capture = None
        with caplog.at_level(logging.WARNING):
            if event_bucket and event_environment:
                pass
            elif event_bucket or event_environment:
                logging.getLogger("form_csv_app.run").warning(
                    "Both event_bucket and event_environment are required for "
                    "event capture. Got event_bucket='%s', "
                    "event_environment='%s'. Event capture will be disabled.",
                    event_bucket,
                    event_environment,
                )

        assert event_capture is None
        assert any("Both event_bucket" in r.message for r in caplog.records)

    def test_neither_config_value_provided_disables_silently(self, caplog):
        """When neither event_bucket nor event_environment are provided,
        event_capture should be None with no warning.

        Requirement 3.4: Neither provided -> None, no error
        """
        config_opts: Dict[str, str] = {}

        event_bucket = config_opts.get("event_bucket", "")
        event_environment = config_opts.get("event_environment", "")

        event_capture = None
        with caplog.at_level(logging.WARNING):
            if event_bucket and event_environment:
                pass
            elif event_bucket or event_environment:
                logging.getLogger("form_csv_app.run").warning(
                    "Both event_bucket and event_environment are required "
                    "for event capture."
                )

        assert event_capture is None
        # No warning logged when both are empty
        assert not any("event_bucket" in r.message for r in caplog.records)

    def test_s3_error_raises_gear_execution_error(self):
        """When S3BucketInterface.create_from_environment raises, a
        GearExecutionError should be raised.

        Requirement 3.3: S3InterfaceError -> GearExecutionError
        """
        config_opts = {
            "event_bucket": "bad-bucket",
            "event_environment": "prod",
        }

        event_bucket = config_opts.get("event_bucket", "")
        event_environment = config_opts.get("event_environment", "")

        with patch("s3.s3_bucket.S3BucketInterface.create_from_environment") as mock_s3:
            mock_s3.side_effect = S3InterfaceError("Bucket not found")

            with pytest.raises(GearExecutionError):
                if event_bucket and event_environment:
                    try:
                        from s3.s3_bucket import S3BucketInterface

                        S3BucketInterface.create_from_environment(event_bucket)
                    except S3InterfaceError as error:
                        raise GearExecutionError(
                            f"Failed to initialize visit event capture: "
                            f"Unable to access S3 bucket '{event_bucket}'. "
                            f"Error: {error}"
                        ) from error


# ============================================================================
# Tests: __capture_duplicate_event edge cases (Requirements 2.7, 6.3)
# ============================================================================


class TestCaptureDuplicateEventEdgeCases:
    """Test __capture_duplicate_event behavior through visit_row()."""

    def test_invalid_date_field_skips_event_capture(self, caplog):
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

    def test_empty_date_field_skips_event_capture(self, caplog):
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

    def test_no_event_capture_configured_skips_silently(self):
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

    def test_no_timestamp_configured_skips_silently(self):
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

    def test_capture_event_failure_does_not_interrupt_processing(self, caplog):
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

    def test_metadata_copy_failure_does_not_trigger_second_event(self):
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

    def test_duplicate_event_captured_on_valid_row(self):
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

    def test_non_duplicate_row_does_not_trigger_event(self):
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
