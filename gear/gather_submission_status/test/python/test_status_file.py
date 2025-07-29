from csv import DictReader, DictWriter
from io import StringIO

from gather_submission_status_app.main import StatusRequest


class TestSubmissionStatus:
    def test_query(self):
        query = StatusRequest(adcid=0, naccid="NACC000000", study="adrc")
        output_stream = StringIO()
        writer = DictWriter(
            output_stream, fieldnames=StatusRequest.model_fields, dialect="unix"
        )
        writer.writeheader()
        writer.writerow(query.model_dump())

        assert output_stream.getvalue() == (
            '"adcid","naccid","study"\n' '"0","NACC000000","adrc"\n'
        )

        output_stream.seek(0)
        reader = DictReader(output_stream)
        row = reader.__next__()
        print(row)
        row_query = StatusRequest.model_validate(row)
        assert query == row_query
