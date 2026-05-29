"""Property-based tests for Pipeline Event Logger.

Feature: pipeline-event-logger
Uses Hypothesis to validate correctness properties from the design document.
"""

from datetime import datetime
from unittest.mock import Mock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import QCStatus
from pipeline_event_logger_app.main import (
    _QC_STATUS_TO_OUTCOME_KEY,
    PipelineEventLogger,
)
from pipeline_event_logger_test.test_factories import (
    build_data_identification_dict,
    build_qc_info,
    create_mock_file_entry,
    create_mock_project_adaptor,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Gear names: non-empty alphanumeric strings with hyphens/underscores
gear_name_strategy = st.from_regex(r"[a-z][a-z0-9_-]{0,30}", fullmatch=True)

# QC statuses as used in the system
qc_status_strategy = st.sampled_from(["PASS", "FAIL", "IN REVIEW"])

# Event action strings (e.g., "pass-qc", "not-pass-qc", "submit")
event_action_strategy = st.from_regex(r"[a-z][a-z0-9-]{0,20}", fullmatch=True)

# Outcome keys used in event_actions mapping
outcome_key_strategy = st.sampled_from(["pass", "fail", "in-review"])

# Datetimes within a reasonable range for timestamps
reasonable_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)


def _build_full_info(
    gear_name: str,
    *,
    status: QCStatus = "PASS",
    errors: list | None = None,
    validated_timestamp: str | None = "2024-06-15 10:30:00",
) -> dict:
    """Build a complete file.info dict with QC and data_identification."""
    info = build_qc_info(gear_name, status=status, errors=errors)
    info["data_identification"] = build_data_identification_dict()
    if validated_timestamp is not None:
        info["validated-timestamp"] = validated_timestamp
    return info


# ===========================================================================
# Property 1: Upstream gear name attribution
# Feature: pipeline-event-logger, Property 1
# ===========================================================================


class TestPropertyUpstreamGearNameAttribution:
    """For any valid upstream gear name, the gear_name passed to
    QCStatusLogManager.update_qc_log equals the upstream gear name, never
    'pipeline-event-logger'.

    Validates: Requirements 3.3
    """

    @settings(max_examples=100)
    @given(upstream_name=gear_name_strategy)
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_gear_name_attribution(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        upstream_name: str,
    ) -> None:
        """gear_name passed to update_qc_log is always the upstream gear
        name."""
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = "qc-log.csv"
        mock_qc_manager_cls.return_value = mock_qc_manager

        info = _build_full_info(upstream_name, status="PASS")
        file_entry = create_mock_file_entry(info=info)
        project = create_mock_project_adaptor()

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=project,
            upstream_gear_name=upstream_name,
            event_capture=None,
            event_actions={},
        )

        logger.run()

        call_kwargs = mock_qc_manager.update_qc_log.call_args.kwargs
        assert call_kwargs["gear_name"] == upstream_name
        assert call_kwargs["gear_name"] != "pipeline-event-logger"


# ===========================================================================
# Property 2: Event action selected by QC outcome
# Feature: pipeline-event-logger, Property 2
# ===========================================================================


class TestPropertyEventActionSelection:
    """For any valid combination of QC status and event_actions mapping, the
    captured event's action matches the mapped value, and gear_name equals the
    upstream gear name. If the outcome key is absent from event_actions, no
    event is captured.

    Validates: Requirements 4.1, 4.2, 4.4, 3.3
    """

    @settings(max_examples=100)
    @given(
        qc_status=qc_status_strategy,
        upstream_name=gear_name_strategy,
        event_actions=st.dictionaries(
            keys=outcome_key_strategy,
            values=event_action_strategy,
            min_size=0,
            max_size=3,
        ),
    )
    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_event_action_matches_mapping(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
        qc_status: QCStatus,
        upstream_name: str,
        event_actions: dict[str, str],
    ) -> None:
        """Event action matches the mapped value for the QC outcome, or no
        event is captured if unmapped."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_visit_event = Mock()
        mock_create_event.return_value = mock_visit_event

        mock_event_capture = Mock()

        info = _build_full_info(upstream_name, status=qc_status)
        file_entry = create_mock_file_entry(info=info)
        project = create_mock_project_adaptor()

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=project,
            upstream_gear_name=upstream_name,
            event_capture=mock_event_capture,
            event_actions=event_actions,
        )

        mock_create_event.reset_mock()
        mock_event_capture.reset_mock()

        logger.run()

        outcome_key = _QC_STATUS_TO_OUTCOME_KEY.get(qc_status)
        expected_action = event_actions.get(outcome_key) if outcome_key else None

        if expected_action is not None:
            # Event should have been created with the correct action and gear name
            mock_create_event.assert_called_once()
            call_kwargs = mock_create_event.call_args.kwargs
            assert call_kwargs["action"] == expected_action
            assert call_kwargs["gear_name"] == upstream_name
        else:
            # No event should have been created
            mock_create_event.assert_not_called()


# ===========================================================================
# Property 3: Timestamp resolution prefers validated-timestamp
# Feature: pipeline-event-logger, Property 3
# ===========================================================================


class TestPropertyTimestampResolution:
    """For any file entry, if validated-timestamp is present and parseable, the
    resolved timestamp equals the parsed value. If absent, it equals
    file.modified.

    Validates: Requirements 5.1, 5.2
    """

    @settings(max_examples=100)
    @given(
        validated_ts=reasonable_datetimes,
        file_modified=reasonable_datetimes,
    )
    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_validated_timestamp_preferred(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
        validated_ts: datetime,
        file_modified: datetime,
    ) -> None:
        """When validated-timestamp is present, it is used over
        file.modified."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_create_event.return_value = Mock()

        ts_str = validated_ts.strftime("%Y-%m-%d %H:%M:%S")
        info = _build_full_info("gear", status="PASS", validated_timestamp=ts_str)
        file_entry = create_mock_file_entry(info=info, modified=file_modified)
        project = create_mock_project_adaptor()
        mock_event_capture = Mock()

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=project,
            upstream_gear_name="gear",
            event_capture=mock_event_capture,
            event_actions={"pass": "pass-qc"},
        )

        logger.run()

        # Verify the timestamp passed to create_visit_event
        call_kwargs = mock_create_event.call_args.kwargs
        expected = validated_ts.replace(microsecond=0)
        assert call_kwargs["completion_time"] == expected

    @settings(max_examples=100)
    @given(file_modified=reasonable_datetimes)
    @patch("pipeline_event_logger_app.main.create_visit_event")
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_file_modified_fallback(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        mock_create_event: Mock,
        file_modified: datetime,
    ) -> None:
        """When validated-timestamp is absent, file.modified is used."""
        mock_qc_manager_cls.return_value = Mock(
            update_qc_log=Mock(return_value="log.csv")
        )
        mock_create_event.return_value = Mock()

        info = _build_full_info("gear", status="PASS", validated_timestamp=None)
        file_entry = create_mock_file_entry(info=info, modified=file_modified)
        project = create_mock_project_adaptor()
        mock_event_capture = Mock()

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=project,
            upstream_gear_name="gear",
            event_capture=mock_event_capture,
            event_actions={"pass": "pass-qc"},
        )

        logger.run()

        # Verify the timestamp passed to create_visit_event
        call_kwargs = mock_create_event.call_args.kwargs
        assert call_kwargs["completion_time"] == file_modified


# ===========================================================================
# Property 4: QC metadata extraction round-trip
# Feature: pipeline-event-logger, Property 4
# ===========================================================================


class TestPropertyQCMetadataRoundTrip:
    """For any valid FileQCModel containing a gear entry, extracting QC status
    and errors via run() produces the same status that was stored in the model.

    Validates: Requirements 1.1, 1.2
    """

    @settings(max_examples=100)
    @given(
        qc_status=qc_status_strategy,
        upstream_name=gear_name_strategy,
    )
    @patch("pipeline_event_logger_app.main.QCStatusLogManager")
    @patch("pipeline_event_logger_app.main.FileVisitAnnotator")
    @patch("pipeline_event_logger_app.main.ErrorLogTemplate")
    def test_qc_extraction_round_trip(
        self,
        mock_template_cls: Mock,
        mock_annotator_cls: Mock,
        mock_qc_manager_cls: Mock,
        qc_status: QCStatus,
        upstream_name: str,
    ) -> None:
        """Extracted QC status passed to update_qc_log matches what was stored
        in the model."""
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = "qc-log.csv"
        mock_qc_manager_cls.return_value = mock_qc_manager

        info = _build_full_info(upstream_name, status=qc_status, errors=[])
        file_entry = create_mock_file_entry(info=info)
        project = create_mock_project_adaptor()

        logger = PipelineEventLogger(
            file_entry=file_entry,
            project=project,
            upstream_gear_name=upstream_name,
            event_capture=None,
            event_actions={},
        )

        logger.run()

        call_kwargs = mock_qc_manager.update_qc_log.call_args.kwargs
        assert call_kwargs["status"] == qc_status
