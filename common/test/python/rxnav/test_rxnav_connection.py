"""Tests the RxNav API, which is public so doesn't need any authorization."""

from datetime import date

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

    def test_is_rxcui_active(self):
        """
        Test the is_rxcui_active method - uses same examples defined on
        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getRxcuiHistoryStatus.html
        """
        # Active (start date of 082016 and no end date)
        assert RxCuiConnection.is_rxcui_active(1801289, date(2026, 4, 16))
        assert RxCuiConnection.is_rxcui_active(1801289)

        # Obsolete (start date 092009 end date 062017); test start month same
        assert RxCuiConnection.is_rxcui_active(861765, date(2009, 9, 1))
        assert not RxCuiConnection.is_rxcui_active(861765, date(2017, 7, 5))
        assert not RxCuiConnection.is_rxcui_active(861765)

        # Remapped (start date 042005 end date 052009); test comfortably in between
        assert RxCuiConnection.is_rxcui_active(105048, date(2007, 5, 10))
        assert not RxCuiConnection.is_rxcui_active(105048, date(2004, 5, 10))
        assert not RxCuiConnection.is_rxcui_active(105048)

        # Quantified (start date 122012 end date 012013); test end month same
        assert RxCuiConnection.is_rxcui_active(1360201, date(2013, 1, 30))
        assert not RxCuiConnection.is_rxcui_active(1360201, date(2025, 2, 2))
        assert not RxCuiConnection.is_rxcui_active(1360201)

        # Not current (no start or end date)
        assert not RxCuiConnection.is_rxcui_active(3686, date(2010, 2, 9))
        assert not RxCuiConnection.is_rxcui_active(3686)

        # Unknown (also no start or end date)
        assert not RxCuiConnection.is_rxcui_active(0, date(2010, 2, 9))
        assert not RxCuiConnection.is_rxcui_active(0)

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
