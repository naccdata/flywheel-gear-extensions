from data_requests.status_request import StatusRequest


class TestStatusRequest:

    def test_case(self):
        request = StatusRequest.model_validate({"AdCiD": 0, "Ptid": "00000"})
        assert request == StatusRequest(adcid=0, ptid="00000")
