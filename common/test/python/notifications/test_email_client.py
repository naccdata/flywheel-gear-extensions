import os

import boto3
import pytest
from moto import mock_aws
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.ses.models import ses_backends
from notifications.email import DestinationModel, EmailClient, TemplateDataModel


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


@mock_aws
class TestEmailClient:
    def test_client(self, ses):
        backend = ses_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
        backend.addresses.append("dummy@dummy.org")
        backend.add_template(
            {
                "template_name": "dummy",
                "subject_part": "blah",
                "html_part": "blah",
                "text_part": "blah",
            }
        )
        email_client = EmailClient(client=ses, source="dummy@dummy.org")
        response = email_client.send(
            configuration_set_name="blah",
            destination=DestinationModel(to_addresses=["dummy@dummy.dummy"]),
            template="dummy",
            template_data=TemplateDataModel(
                firstname="dummy", email_address="dummy@dummy.com"
            ),
        )
        assert response
