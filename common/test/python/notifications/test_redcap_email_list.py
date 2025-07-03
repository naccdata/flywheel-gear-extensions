"""Tests REDCapEmailList."""

from typing import Dict, List

import pytest
from notifications.redcap_email_list import REDCapEmailList
from redcap_api.redcap_connection import REDCapReportConnection


@pytest.fixture(scope="function")
def redcap_email_list():
    """Fixture for REDCapEmailList."""
    redcap_con = MockREDCapReportConnection(
        token="dummy-token", url="dummy-url", report_id=0
    )
    return REDCapEmailList(redcap_con=redcap_con, email_key="email")


class MockREDCapReportConnection(REDCapReportConnection):
    """Mocks the REDCap connection for testing."""

    def get_report_records(self) -> List[Dict[str, str]]:
        """Mock getting report records."""
        return [
            {"email": "dummy_email1@dummy.org", "firstname": "Dummy1"},
            {"email": "dummy_email2@dummy.org", "firstname": "Dummy2"},
            {"email": "dummy_email3@dummy.org", "firstname": "Dummy3"},
        ]


class TestREDCapEmailList:
    def test_grabbed_email_list(self, redcap_email_list):
        assert redcap_email_list.email_list == {
            "dummy_email1@dummy.org": {
                "email": "dummy_email1@dummy.org",
                "firstname": "Dummy1",
            },
            "dummy_email2@dummy.org": {
                "email": "dummy_email2@dummy.org",
                "firstname": "Dummy2",
            },
            "dummy_email3@dummy.org": {
                "email": "dummy_email3@dummy.org",
                "firstname": "Dummy3",
            },
        }
