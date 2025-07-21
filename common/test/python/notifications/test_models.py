from notifications.email import DestinationModel


class TestEmailClientModels:
    def test_destination(self):
        dest = DestinationModel(to_addresses=["dummy@dummy.dummy"])
        assert dest.model_dump(by_alias=True, exclude_none=True) == {
            "ToAddresses": ["dummy@dummy.dummy"]
        }
