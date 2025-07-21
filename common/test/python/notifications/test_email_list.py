import os

import boto3
import pytest
from moto import mock_aws
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.ses.models import ses_backends
from notifications.email_list import (
    EmailListClient,
    EmailListConfigs,
)


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
def email_list():
    return {
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


@pytest.fixture(scope="function")
def email_list_client(ses, email_list):
    """Fixture for EmailListClient."""
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

    configs = EmailListConfigs(
        source_email="dummy@dummy.org",
        configuration_set_name="test_configuration",
        template_name="dummy_template",
        firstname_key="firstname",
    )

    return EmailListClient(client=ses, email_list=email_list, configs=configs)


@mock_aws
class TestEmailListClient:
    def test_send_mass_email(self, email_list_client):
        response = email_list_client.send_mass_email()
        assert response

    def test_send_emails(self, email_list_client):
        responses = email_list_client.send_emails()
        assert responses and set(responses.keys()) == {
            "dummy_email1@dummy.org",
            "dummy_email2@dummy.org",
            "dummy_email3@dummy.org",
        }
