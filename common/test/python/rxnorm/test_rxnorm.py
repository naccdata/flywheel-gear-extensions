"""Tests the RxNav API, which is public so doesn't need any authorization."""

from RxNav.RxNav_connection import RxcuiStatus, RxNavConnection


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
        assert RxNavConnection.get_rxcui_status(1801289) == RxcuiStatus.ACTIVE
        assert RxNavConnection.get_rxcui_status(861765) == RxcuiStatus.OBSOLETE
        assert RxNavConnection.get_rxcui_status(105048) == RxcuiStatus.REMAPPED
        assert RxNavConnection.get_rxcui_status(1360201) == RxcuiStatus.QUANTIFIED
        assert RxNavConnection.get_rxcui_status(3686) == RxcuiStatus.NOT_CURRENT
        assert RxNavConnection.get_rxcui_status(0) == RxcuiStatus.UNKNOWN
