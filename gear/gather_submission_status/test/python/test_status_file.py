from csv import DictReader, DictWriter
from io import StringIO

from data_requests.status_request import StatusRequest


class TestSubmissionStatus:
    def test_query_without_study(self):
        query = StatusRequest(adcid=0, ptid="NACC000000")
        output_stream = StringIO()
        fieldnames = set(StatusRequest.model_fields.keys()).difference({"study"})
        writer = DictWriter(output_stream, fieldnames=fieldnames, dialect="unix")
        writer.writeheader()
        writer.writerow(query.model_dump(exclude_none=True))

        assert output_stream.getvalue() == ('"adcid","ptid"\n"0","NACC000000"\n')

        output_stream.seek(0)
        reader = DictReader(output_stream)
        row = reader.__next__()
        print(row)
        row_query = StatusRequest.model_validate(row)
        assert query == row_query

    def test_query_with_study(self):
        query = StatusRequest(adcid=0, ptid="NACC000000", study="adrc")
        output_stream = StringIO()
        fieldnames = list(StatusRequest.model_fields.keys())
        writer = DictWriter(output_stream, fieldnames=fieldnames, dialect="unix")
        writer.writeheader()
        writer.writerow(query.model_dump(exclude_none=True))

        assert output_stream.getvalue() == (
            '"adcid","ptid","study"\n"0","NACC000000","adrc"\n'
        )

        output_stream.seek(0)
        reader = DictReader(output_stream)
        row = reader.__next__()
        print(row)
        row_query = StatusRequest.model_validate(row)
        assert query == row_query
