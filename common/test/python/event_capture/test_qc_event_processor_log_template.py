"""Tests for the QC status log naming in QCEventProcessor."""

from unittest.mock import Mock

from configs.ingest_configs import FormProjectConfigs
from error_logging.error_logger import ErrorLogTemplate
from event_capture.event_processor import QCEventProcessor
from nacc_common.data_identification import DataIdentification

DATA_ID = DataIdentification.from_visit_metadata(
    adcid=42, ptid="1010", date="2024-01-15", visitnum="1", module="UDS"
)


def create_processor(project: Mock, form_configs=None) -> QCEventProcessor:
    return QCEventProcessor(
        project=project,
        event_generator=Mock(),
        unmatched_events=Mock(),
        event_capture=None,
        dry_run=True,
        form_configs=form_configs,
    )


class TestQCEventProcessorLogTemplate:
    def test_default_log_template(self):
        project = Mock()
        processor = create_processor(project)
        processor._find_qc_status_for_visit(DATA_ID)  # noqa: SLF001
        project.get_file.assert_any_call("1010_2024-01-15_1_uds_qc-status.log")

    def test_configured_log_template(self):
        project = Mock()
        form_configs = FormProjectConfigs(
            primary_key="naccid",
            accepted_modules=[],
            module_configs={},
            errorlog_template=ErrorLogTemplate(suffix="update-request"),
        )
        processor = create_processor(project, form_configs)
        processor._find_qc_status_for_visit(DATA_ID)  # noqa: SLF001
        project.get_file.assert_any_call("1010_2024-01-15_1_uds_update-request.log")
