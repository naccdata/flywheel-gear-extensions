from identifiers.model import CenterFields


class TestIdentifierModels:

    def test_center_fields(self):
        messy_ptid = CenterFields(adcid=0, ptid=' 01 ')
        assert messy_ptid.ptid == '1'
