import os
from typing import Dict, List

import boto3
import pytest
from moto import mock_aws
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.ses.models import ses_backends
from notifications.redcap_email_list import REDCapEmailList, REDCapEmailListConfigs
from redcap_api.redcap_connection import REDCapReportConnection


@pytest.fixture(scope="function")
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def ses(aws_credentials):
    """Fixture for mocking SES service."""
    with mock_aws():
        yield boto3.client("ses", region_name="us-east-1")  # types: ignore


@pytest.fixture(scope="function")
def redcap_email_list(ses):
    """Fixture for REDCapEmailList."""
    backend = ses_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    backend.addresses.append("dummy@dummy.org")
    backend.add_template(
        {
            "template_name": "dummy_template",
            "subject_part": "blah",
            "html_part": "blah",
            "text_part": "blah",
        }
    )

    redcap_con = MockREDCapReportConnection(
        token="dummy-token", url="dummy-url", report_id=0
    )
    configs = REDCapEmailListConfigs(
        redcap_parameter_path="/dummy",
        source_email="dummy@dummy.org",
        configuration_set_name="test_configuration",
        template_name="dummy_template",
        firstname_key="firstname",
    )

    return REDCapEmailList(redcap_con=redcap_con, configs=configs, ses=ses)


class MockREDCapReportConnection(REDCapReportConnection):
    """Mocks the REDCap connection for testing."""

    def get_report_records(self) -> List[Dict[str, str]]:
        """Mock getting report records."""
        return [
            {"email": "dummy_email1@dummy.org", "firstname": "Dummy1"},
            {"email": "dummy_email2@dummy.org", "firstname": "Dummy2"},
            {"email": "dummy_email3@dummy.org", "firstname": "Dummy3"},
        ]


@mock_aws
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

    def test_send_mass_email(self, redcap_email_list):
        response = redcap_email_list.send_mass_email()
        assert response

    def test_send_emails(self, redcap_email_list):
        responses = redcap_email_list.send_emails()
        assert responses and set(responses.keys()) == {
            "dummy_email1@dummy.org",
            "dummy_email2@dummy.org",
            "dummy_email3@dummy.org",
        }
