from nacc_common.error_data import ERROR_HEADER_NAMES, STATUS_HEADER_NAMES
from outputs.visit_submission_error import ErrorReportModel
from outputs.visit_submission_status import StatusReportModel


class TestErrorData:
    def test_error_header_names(self):
        assert ERROR_HEADER_NAMES is not None
        assert ERROR_HEADER_NAMES != []
        assert ErrorReportModel.serialized_fieldnames() == ERROR_HEADER_NAMES

    def test_status_header_names(self):
        assert STATUS_HEADER_NAMES is not None
        assert STATUS_HEADER_NAMES != []
        assert list(StatusReportModel.model_fields.keys()) == STATUS_HEADER_NAMES
