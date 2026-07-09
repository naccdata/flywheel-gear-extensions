"""Unit tests for PipelineEventLogger business logic."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from gear_execution.gear_execution import GearExecutionError
from nacc_common.error_models import QCStatus
from pipeline_event_logger_app.main import PipelineEventLogger
from pipeline_event_logger_test.test_factories import (
    build_data_identification_dict,
    build_qc_info,
    create_mock_file_entry,
    create_mock_project_adaptor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_full_info(
    gear_name: str,
    *,
    status: QCStatus = "PASS",
    errors: list | None = None,
    data_identification: dict | None = None,
    validated_timestamp: str | None = "2024-06-15 10:30:00",
) -> dict:
    """Build a complete file.info dict with QC, data_identification, and
    optional timestamp."""
    info = build_qc_info(gear_name, status=status, errors=errors)
    info["data_identification"] = (
        data_identification
        if data_identification is not None
        else build_data_identification_dict()
    )
    if validated_timestamp is not None:
        info["validated-timestamp"] = validated_timestamp
    return info


def _make_logger(
    *,
    upstream_gear_name: str = "test-upstream-gear",
    file_info: dict | None = None,
    event_capture: Mock | None = None,
    event_actions: dict[str, str] | None = None,
    file_modified: datetime | None = None,
    dry_run: bool = False,
) -> PipelineEventLogger:
    """Build a PipelineEventLogger with sensible defaults."""
    info = file_info if file_info is not None else {}
    file_entry = create_mock_file_entry(
        info=info,
        modified=file_modified or datetime(2024, 6, 15, 10, 30, 0),
    )
    project = create_mock_project_adaptor()
    return PipelineEventLogger(
        file_entry=file_entry,
        project=project,
        upstream_gear_name=upstream_gear_name,
        event_capture=event_capture,
        event_actions=event_actions or {},
        dry_run=dry_run,
    )


# ===========================================================================
# Tests for QC metadata reading via run()
# ===========================================================================


class TestQCMetadataReading:
    """Tests that run() correctly reads and validates QC metadata."""

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_valid_pass_status_completes(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """run() completes successfully with valid PASS QC metadata."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "my-gear"
        info = _build_full_info(gear, status="PASS", errors=[])
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()  # Should not raise

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_valid_fail_status_completes(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """run() completes successfully with valid FAIL QC metadata and
        errors."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "my-gear"
        errors = [
            {
                "type": "error",
                "code": "E001",
                "message": "some error",
                "location": {"line": 1, "column_name": "field"},
            }
        ]
        info = _build_full_info(gear, status="FAIL", errors=errors)
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()  # Should not raise

    def test_missing_info_raises(self) -> None:
        """run() raises GearExecutionError when file.info is missing."""
        file_entry = create_mock_file_entry(info=None)
        file_entry.reload.return_value = file_entry
        file_entry.info = None

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=create_mock_project_adaptor(),
            upstream_gear_name="gear",
            event_capture=None,
            event_actions={},
        )

        with pytest.raises(GearExecutionError, match=r"file\.info is empty"):
            logger.run()

    def test_missing_qc_section_raises(self) -> None:
        """run() raises GearExecutionError when file.info.qc is missing."""
        info: dict = {
            "some_key": "value",
            "data_identification": build_data_identification_dict(),
        }
        logger = _make_logger(upstream_gear_name="gear", file_info=info)

        with pytest.raises(GearExecutionError, match=r"file\.info\.qc not found"):
            logger.run()

    def test_missing_upstream_gear_in_qc_raises(self) -> None:
        """run() raises GearExecutionError when upstream gear entry is missing
        from file.info.qc."""
        info = _build_full_info("other-gear", status="PASS")
        logger = _make_logger(upstream_gear_name="my-gear", file_info=info)

        with pytest.raises(GearExecutionError, match=r"not found in file\.info\.qc"):
            logger.run()

    def test_invalid_qc_structure_raises(self) -> None:
        """run() raises GearExecutionError when QC structure is invalid."""
        info: dict = {
            "qc": "not-a-dict",
            "data_identification": build_data_identification_dict(),
        }
        logger = _make_logger(upstream_gear_name="gear", file_info=info)

        with pytest.raises(GearExecutionError, match=r"file\.info\.qc not found"):
            logger.run()


# ===========================================================================
# Tests for data identification reading via run()
# ===========================================================================


class TestDataIdentificationReading:
    """Tests that run() correctly reads and validates data identification."""

    def test_missing_data_identification_raises(self) -> None:
        """run() raises GearExecutionError when data_identification is
        missing."""
        gear = "gear"
        info = build_qc_info(gear, status="PASS")
        # No data_identification key
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        with pytest.raises(
            GearExecutionError, match=r"file\.info\.data_identification not found"
        ):
            logger.run()

    def test_invalid_data_identification_raises(self) -> None:
        """run() raises GearExecutionError when data_identification is
        invalid."""
        gear = "gear"
        info = build_qc_info(gear, status="PASS")
        info["data_identification"] = {"invalid_field": "value"}
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        with pytest.raises(GearExecutionError, match="Invalid data_identification"):
            logger.run()

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_valid_form_data_identification(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """run() completes with valid form data_identification (module)."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "gear"
        data_id_dict = build_data_identification_dict(
            ptid="110001", adcid=42, date="2024-06-15", module="UDS", visitnum="1"
        )
        info = _build_full_info(gear, data_identification=data_id_dict)
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()  # Should not raise

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_valid_imaging_data_identification(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """run() completes with valid imaging data_identification
        (modality)."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "gear"
        data_id_dict = build_data_identification_dict(
            ptid="110001",
            adcid=42,
            date="2024-06-15",
            module=None,
            modality="MR",
            visitnum=None,
        )
        info = _build_full_info(gear, data_identification=data_id_dict)
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()  # Should not raise


# ===========================================================================
# Tests for timestamp resolution via run()
# ===========================================================================


class TestTimestampResolution:
    """Tests that run() correctly resolves timestamps."""

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_validated_timestamp_used_in_event(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """When validated-timestamp is present, it is used for event
        capture."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_create_event.return_value = Mock()

        gear = "gear"
        mock_event_capture = Mock()
        info = _build_full_info(
            gear, status="PASS", validated_timestamp="2024-06-15 10:30:00"
        )
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions={"pass": "pass-qc"},
            file_modified=datetime(2024, 1, 1, 0, 0, 0),
        )

        logger.run()

        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["completion_time"] == datetime(2024, 6, 15, 10, 30, 0)

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_file_modified_fallback_used_in_event(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """When validated-timestamp is absent, file.modified is used for event
        capture."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_create_event.return_value = Mock()

        gear = "gear"
        file_modified = datetime(2024, 1, 1, 12, 0, 0)
        mock_event_capture = Mock()
        info = _build_full_info(gear, status="PASS", validated_timestamp=None)
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions={"pass": "pass-qc"},
            file_modified=file_modified,
        )

        logger.run()

        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["completion_time"] == file_modified


# ===========================================================================
# Tests for QC status log update via run()
# ===========================================================================


class TestQCStatusLogUpdate:
    """Tests that run() correctly updates the QC status log."""

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_upstream_gear_name_attributed(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """QC log entry is attributed to the upstream gear name, not pipeline-
        event-logger."""
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = "test-qc-log.csv"
        mock_qc_manager_cls.return_value = mock_qc_manager

        gear = "my-upstream-gear"
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()

        mock_qc_manager.update_qc_log.assert_called_once()
        call_kwargs = mock_qc_manager.update_qc_log.call_args.kwargs
        assert call_kwargs["gear_name"] == gear
        assert call_kwargs["gear_name"] != "pipeline-event-logger"
        assert call_kwargs["status"] == "PASS"
        assert call_kwargs["add_visit_metadata"] is True

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_qc_log_failure_is_non_critical(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """QC log update failure does not cause run() to raise."""
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.side_effect = RuntimeError("QC log error")
        mock_qc_manager_cls.return_value = mock_qc_manager

        gear = "my-upstream-gear"
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(upstream_gear_name=gear, file_info=info)

        logger.run()  # Should not raise


# ===========================================================================
# Tests for event capture via run()
# ===========================================================================


class TestEventCapture:
    """Tests that run() correctly captures events."""

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_pass_status_captures_pass_action(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """PASS status selects the 'pass' action from event_actions."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_visit_event = Mock()
        mock_create_event.return_value = mock_visit_event

        gear = "my-upstream-gear"
        mock_event_capture = Mock()
        actions = {"pass": "pass-qc", "fail": "not-pass-qc"}
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
        )

        logger.run()

        mock_create_event.assert_called_once()
        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["action"] == "pass-qc"
        assert call_kwargs["gear_name"] == gear
        mock_event_capture.capture_event.assert_called_once_with(mock_visit_event)

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_fail_status_captures_fail_action(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """FAIL status selects the 'fail' action from event_actions."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_visit_event = Mock()
        mock_create_event.return_value = mock_visit_event

        gear = "my-upstream-gear"
        mock_event_capture = Mock()
        actions = {"pass": "pass-qc", "fail": "not-pass-qc"}
        info = _build_full_info(gear, status="FAIL")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
        )

        logger.run()

        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["action"] == "not-pass-qc"
        assert call_kwargs["gear_name"] == gear

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_no_event_when_action_not_mapped(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """No event captured when outcome key is not in event_actions."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "my-upstream-gear"
        mock_event_capture = Mock()
        actions = {"pass": "pass-qc"}  # No "fail" mapping
        info = _build_full_info(gear, status="FAIL")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
        )

        logger.run()

        mock_create_event.assert_not_called()
        mock_event_capture.capture_event.assert_not_called()

    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_no_event_when_capture_not_configured(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
    ) -> None:
        """No event captured when event_capture is None."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )

        gear = "my-upstream-gear"
        actions = {"pass": "pass-qc"}
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=None,
            event_actions=actions,
        )

        logger.run()  # Should complete without attempting event capture

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_event_capture_failure_is_non_critical(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """Event capture failure does not cause run() to raise."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_create_event.return_value = Mock()

        gear = "my-upstream-gear"
        mock_event_capture = Mock()
        mock_event_capture.capture_event.side_effect = RuntimeError("S3 error")
        actions = {"pass": "pass-qc"}
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
        )

        logger.run()  # Should not raise

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_upstream_gear_name_used_in_event(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """Event uses upstream gear name, not 'pipeline-event-logger'."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_visit_event = Mock()
        mock_create_event.return_value = mock_visit_event

        gear = "custom-upstream-gear"
        mock_event_capture = Mock()
        actions = {"pass": "pass-qc"}
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
        )

        logger.run()

        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["gear_name"] == "custom-upstream-gear"
        assert call_kwargs["gear_name"] != "pipeline-event-logger"


# ===========================================================================
# Tests for dry_run mode via run()
# ===========================================================================


class TestDryRun:
    """Tests that dry_run mode skips write operations."""

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_dry_run_skips_qc_log_update(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """dry_run=True skips QC status log update."""
        mock_qc_manager = Mock()
        mock_qc_manager_cls.return_value = mock_qc_manager

        gear = "my-upstream-gear"
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            dry_run=True,
        )

        logger.run()

        mock_qc_manager.update_qc_log.assert_not_called()

    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_dry_run_skips_event_capture(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
    ) -> None:
        """dry_run=True skips event capture."""
        gear = "my-upstream-gear"
        mock_event_capture = Mock()
        actions = {"pass": "pass-qc"}
        info = _build_full_info(gear, status="PASS")
        logger = _make_logger(
            upstream_gear_name=gear,
            file_info=info,
            event_capture=mock_event_capture,
            event_actions=actions,
            dry_run=True,
        )

        logger.run()

        mock_create_event.assert_not_called()
        mock_event_capture.capture_event.assert_not_called()

    def test_dry_run_still_reads_qc_metadata(self) -> None:
        """dry_run=True still reads and validates QC metadata (critical
        step)."""
        info: dict = {
            "qc": "not-a-dict",
            "data_identification": build_data_identification_dict(),
        }
        logger = _make_logger(
            upstream_gear_name="gear",
            file_info=info,
            dry_run=True,
        )

        with pytest.raises(GearExecutionError, match=r"file\.info\.qc not found"):
            logger.run()
