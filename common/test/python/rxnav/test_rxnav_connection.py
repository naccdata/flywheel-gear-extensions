"""Tests the RxNav API, which is public so doesn't need any authorization."""

from rxnav.rxnav_connection import (
    RxClassConnection,
    RxCuiConnection,
    RxCuiStatus,
    RxNavConnection,
)


class TestRxNavConnection:
    """Tests the RxNavConnection class."""

    def test_url_creation(self):
        """Test URL creation."""
        assert (
            RxNavConnection.url("REST/test/path")
            == "https://rxnav.nlm.nih.gov/REST/test/path"
        )

    def test_get_rxcui_status(self):
        """
        Test the get_rxcui_status method - uses same examples defined on
        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getRxcuiHistoryStatus.html
        """
        assert RxCuiConnection.get_rxcui_status(1801289) == RxCuiStatus.ACTIVE
        assert RxCuiConnection.get_rxcui_status(861765) == RxCuiStatus.OBSOLETE
        assert RxCuiConnection.get_rxcui_status(105048) == RxCuiStatus.REMAPPED
        assert RxCuiConnection.get_rxcui_status(1360201) == RxCuiStatus.QUANTIFIED
        assert RxCuiConnection.get_rxcui_status(3686) == RxCuiStatus.NOT_CURRENT
        assert RxCuiConnection.get_rxcui_status(0) == RxCuiStatus.UNKNOWN

    def test_get_rxclass_members(self):
        """Test the chained result of calling the following APIs:

        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxClass.getClassMembers.html
        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getAllRelatedInfo.html
        """
        result = RxClassConnection.get_all_rxclass_members(["C02L"])
        assert len(result) == 1 and "C02L" in result
        assert len(result["C02L"]) == 127

        # with filtering applied
        result = RxClassConnection.get_all_rxclass_members(
            ["C02L"], combination_rx_classes=["C02L"]
        )
        assert len(result) == 1 and "C02L" in result
        assert len(result["C02L"]) == 89
