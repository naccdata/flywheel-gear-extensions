"""Tests for using the configured QC status log template in form-scheduler."""

from unittest.mock import Mock

from configs.ingest_configs import FormProjectConfigs
from error_logging.error_logger import ErrorLogTemplate
from flywheel.models.file_entry import FileEntry
from form_scheduler_app.event_accumulator import EventAccumulator

FORM_CONFIGS = FormProjectConfigs(
    primary_key="naccid",
    accepted_modules=[],
    module_configs={},
    errorlog_template=ErrorLogTemplate(suffix="update-request"),
)


def create_json_file() -> FileEntry:
    json_file = Mock(spec=FileEntry)
    json_file.reload.return_value = json_file
    json_file.name = "NACC000001_FORMS-VISIT-1_UDS.json"
    json_file.info = {
        "forms": {
            "json": {
                "ptid": "1010",
                "visitdate": "2024-01-15",
                "visitnum": "1",
                "module": "UDS",
                "adcid": 42,
            }
        }
    }
    return json_file


class TestEventAccumulatorLogTemplate:
    def test_default_log_template(self):
        accumulator = EventAccumulator(event_capture=Mock())
        assert (
            accumulator.create_qc_status_file_name(create_json_file())
            == "1010_2024-01-15_1_uds_qc-status.log"
        )

    def test_configured_log_template(self):
        accumulator = EventAccumulator(event_capture=Mock(), form_configs=FORM_CONFIGS)
        assert (
            accumulator.create_qc_status_file_name(create_json_file())
            == "1010_2024-01-15_1_uds_update-request.log"
        )
