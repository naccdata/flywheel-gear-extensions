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

        Asserts structural properties rather than exact counts since the
        RxNav database is updated periodically.
        """
        result = RxClassConnection.get_all_rxclass_members(["C02L"])
        assert len(result) == 1 and "C02L" in result
        members = result["C02L"]
        assert len(members) > 0, "Expected non-empty members for C02L"

        # verify each entry has the expected shape
        for rxcui, data in members.items():
            assert isinstance(rxcui, str) and rxcui.strip(), (
                f"rxcui should be a non-empty string, got {rxcui!r}"
            )
            assert "name" in data and isinstance(data["name"], str)
            assert "tty" in data and isinstance(data["tty"], str)
            assert data["tty"] not in ("DF", "DFG"), (
                f"DF/DFG should be filtered out, found {data['tty']} for {rxcui}"
            )

        # with combination filtering applied, result should be a subset
        filtered_result = RxClassConnection.get_all_rxclass_members(
            ["C02L"], combination_rx_classes=["C02L"]
        )
        assert len(filtered_result) == 1 and "C02L" in filtered_result
        filtered_members = filtered_result["C02L"]
        assert len(filtered_members) > 0, "Expected non-empty filtered members for C02L"
        assert len(filtered_members) < len(members), (
            "Filtered results should be smaller than unfiltered"
        )

        # verify combination filtering removed IN and SCDC types
        for rxcui, data in filtered_members.items():
            assert data["tty"] not in ("IN", "SCDC"), (
                f"IN/SCDC should be filtered for combination classes, "
                f"found {data['tty']} for {rxcui}"
            )
