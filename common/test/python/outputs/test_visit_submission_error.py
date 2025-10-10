from datetime import date

from nacc_common.error_models import CSVLocation, FileError, JSONLocation, VisitKeys
from outputs.visit_submission_error import ErrorReportModel, error_transformer


class TestErrorTransformer:
    def test_valid(self):
        visit = VisitKeys(
            adcid=999, ptid="dummy01", module="UDS", date=date.today().isoformat()
        )
        file_error = FileError(
            timestamp="time",
            error_type="warning",  # pyright: ignore[reportCallIssue]
            error_code="code",  # pyright: ignore[reportCallIssue]
            location=CSVLocation(line=10, column_name="test-column"),
            container_id=None,
            flywheel_path="path",
            message="error message",
            expected="blah",
            ptid="dummy01",
            visitnum="v1",
            date=date.today().isoformat(),
            naccid=None,
        )

        report_model = error_transformer(
            gear_name="stage-test", visit=visit, file_error=file_error
        )
        assert report_model
        assert report_model.adcid == visit.adcid
        assert report_model.timestamp == file_error.timestamp

    def test_fields(self):
        report_fieldnames = set(ErrorReportModel.fieldnames())
        dump_fieldnames = set(ErrorReportModel.serialized_fieldnames())
        location_fieldnames = set(CSVLocation.model_fields.keys()).union(
            set(JSONLocation.model_fields.keys())
        )

        assert dump_fieldnames - report_fieldnames == location_fieldnames

        # assert report_fieldnames ==

        visit = VisitKeys(
            adcid=999, ptid="dummy01", module="UDS", date=date.today().isoformat()
        )
        file_error = FileError(
            timestamp="time",
            error_type="warning",  # pyright: ignore[reportCallIssue]
            error_code="code",  # pyright: ignore[reportCallIssue]
            location=CSVLocation(line=10, column_name="test-column"),
            container_id=None,
            flywheel_path="path",
            message="error message",
            expected="blah",
            ptid="dummy01",
            visitnum="v1",
            date=date.today().isoformat(),
            naccid=None,
        )

        report_model = error_transformer(
            gear_name="stage-test", visit=visit, file_error=file_error
        )
        report_row = report_model.model_dump(by_alias=True)

        report_keys = set(report_row.keys())
        assert report_keys - dump_fieldnames == set()
        assert dump_fieldnames - report_keys == {"key_path"}
