"""Tests the RxNorm API, which is public so doesn't need any authorization."""

from rxnorm.rxnorm_connection import RxcuiStatus, RxNormConnection


class TestRxNormConnection:
    """Tests the RxNormConnection class."""

    def test_url_creation(self):
        """Test URL creation."""
        assert (
            RxNormConnection.url("REST/test/path")
            == "https://rxnav.nlm.nih.gov/REST/test/path"
        )

    def test_get_rxcui_status(self):
        """
        Test the get_rxcui_status method - uses same examples defined on
        https://lhncbc.nlm.nih.gov/RxNav/APIs/api-RxNorm.getRxcuiHistoryStatus.html
        """
        assert RxNormConnection.get_rxcui_status(1801289) == RxcuiStatus.ACTIVE
        assert RxNormConnection.get_rxcui_status(861765) == RxcuiStatus.OBSOLETE
        assert RxNormConnection.get_rxcui_status(105048) == RxcuiStatus.REMAPPED
        assert RxNormConnection.get_rxcui_status(1360201) == RxcuiStatus.QUANTIFIED
        assert RxNormConnection.get_rxcui_status(3686) == RxcuiStatus.NOT_CURRENT
        assert RxNormConnection.get_rxcui_status(0) == RxcuiStatus.UNKNOWN
