from datetime import date

from gather_submission_status_app.visit_submission_error import error_transformer
from outputs.error_models import CSVLocation, FileError, VisitKeys


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
