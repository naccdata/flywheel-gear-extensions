from data_requests.data_request import DataRequest


class TestDataRequest:

    def test_case(self):
        request = DataRequest.model_validate({"NACCID":"NACC000000"})
        assert request == DataRequest(naccid="NACC000000")
