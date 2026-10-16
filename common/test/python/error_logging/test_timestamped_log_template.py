"""Tests for adding the submission timestamp to QC status log names."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from error_logging.error_logger import ErrorLogTemplate, get_submission_timestamp
from error_logging.qc_status_log_creator import QCStatusLogManager
from flywheel.models.file_entry import FileEntry
from keys.keys import MetadataKeys
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ParticipantIdentification,
    VisitIdentification,
)

TIMESTAMP = datetime(2026, 10, 16, 10, 15, 30, tzinfo=timezone.utc)


def create_data_id() -> DataIdentification:
    return DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345", naccid="NACC123"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="UDS", packet="I"),
    )


def create_file(info: dict) -> FileEntry:
    file = Mock(spec=FileEntry)
    file.info = info
    file.created = TIMESTAMP
    return file


class TestTimestampedLogTemplate:
    def test_default_ignores_timestamp(self):
        template = ErrorLogTemplate()
        assert template.instantiate(create_data_id(), TIMESTAMP) == (
            "12345_2024-01-15_001_uds_qc-status.log"
        )

    def test_timestamp_added(self):
        template = ErrorLogTemplate(suffix="update-request", add_timestamp=True)
        assert template.instantiate(create_data_id(), TIMESTAMP) == (
            "12345_2024-01-15_001_uds_20261016T101530Z_update-request.log"
        )
        assert template.instantiate_legacy(create_data_id()) is None

    def test_timestamp_converted_to_utc(self):
        local = TIMESTAMP.astimezone(timezone(timedelta(hours=-7)))
        template = ErrorLogTemplate(add_timestamp=True)
        assert template.instantiate(create_data_id(), local) == (
            "12345_2024-01-15_001_uds_20261016T101530Z_qc-status.log"
        )

    def test_missing_timestamp(self):
        template = ErrorLogTemplate(add_timestamp=True)
        assert template.instantiate(create_data_id()) is None
        assert template.instantiate_legacy(create_data_id()) is None


class TestQCStatusLogManagerTimestamp:
    def test_timestamp_used(self):
        project = Mock()
        project.get_file.return_value = None
        manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(add_timestamp=True),
            visit_annotator=Mock(),
            timestamp=TIMESTAMP,
        )
        assert manager.get_qc_log_filename(create_data_id(), project) == (
            "12345_2024-01-15_001_uds_20261016T101530Z_qc-status.log"
        )
        # no legacy log lookup for timestamped logs
        project.get_file.assert_called_once_with(
            "12345_2024-01-15_001_uds_20261016T101530Z_qc-status.log"
        )

    def test_missing_timestamp(self):
        manager = QCStatusLogManager(
            error_log_template=ErrorLogTemplate(add_timestamp=True),
            visit_annotator=Mock(),
        )
        assert manager.get_qc_log_filename(create_data_id(), Mock()) is None


class TestGetSubmissionTimestamp:
    @pytest.mark.parametrize(
        "value", ["2026-10-15 08:00:00", "2026-10-15T08:00:00+00:00"]
    )
    def test_from_info(self, value: str):
        file = create_file({MetadataKeys.SUBMISSION_TIMESTAMP: value})
        assert get_submission_timestamp(file) == datetime(
            2026, 10, 15, 8, 0, 0, tzinfo=timezone.utc
        )

    def test_from_created(self):
        assert get_submission_timestamp(create_file({})) == TIMESTAMP

    def test_invalid_info(self):
        file = create_file({MetadataKeys.SUBMISSION_TIMESTAMP: "not a timestamp"})
        assert get_submission_timestamp(file) == TIMESTAMP
