"""Tests for parameter store class.

Note: ParameterStore uses boto3 and these tests use moto for mocking.
Moto documentation says imports of boto3 need to occur within scope
where the mock is enabled.
So, imports of ParameterStore are done within tests.
"""

import os

import boto3
import pytest
from moto import mock_aws
from typing_extensions import TypedDict


@pytest.fixture(scope="function")
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


# pylint: disable=(redefined-outer-name,unused-argument)
@pytest.fixture(scope="function")
def ssm(aws_credentials):
    """Fixture for mocking SSM service."""
    with mock_aws():
        yield boto3.client("ssm", region_name="us-east-1")


class TestParameters(TypedDict):
    """Dummy class for testing get_parameters."""

    param1: str
    param2: str


# pylint: disable=(no-self-use)
@mock_aws
class TestParameterStore:
    """Tests for parameter store class."""

    # pylint: disable=(unused-argument,import-outside-toplevel)
    def test_empty(self, aws_credentials):
        """Test what happens when pull from empty store."""
        from inputs.parameter_store import ParameterError, ParameterStore

        store = ParameterStore.create_from_environment()
        assert store

        # TODO: check error message
        with pytest.raises(ParameterError):
            store.get_api_key(path_prefix="/prod/flywheel/gearbot")

    def test_api_key(self, ssm):
        """Test getting api key that is present in store."""
        from inputs.parameter_store import ParameterStore

        prefix = "/prod/flywheel/gearbot"
        ssm.put_parameter(Name=f"{prefix}/apikey", Type="SecureString", Value="dummy")  # type: ignore

        store = ParameterStore.create_from_environment()
        assert store

        value = store.get_api_key(path_prefix=prefix)
        assert value == "dummy"

    def test_dict_parameters(self, ssm):
        """Tests for pulling dictionary of parameters (aka, by path)"""
        from inputs.parameter_store import ParameterError, ParameterStore

        ssm.put_parameter(Name="/test/valid/param1", Type="String", Value="1")
        ssm.put_parameter(Name="/test/valid/param2", Type="String", Value="2")
        ssm.put_parameter(Name="/test/invalid/nonparam1", Type="String", Value="one")

        store = ParameterStore.create_from_environment()
        assert store

        # NOTE: type parameter must be a subtype of typing_extensions.TypeDict
        valid_parameters = store.get_parameters(
            param_type=TestParameters, parameter_path="/test/valid"
        )
        assert valid_parameters
        assert list(valid_parameters.keys()) == ["param1", "param2"]

        # TODO: check error message
        with pytest.raises(ParameterError):
            store.get_parameters(
                param_type=TestParameters, parameter_path="/test/invalid"
            )

    def test_support_emails(self, ssm):
        """Test getting support staff emails from parameter store."""
        from inputs.parameter_store import ParameterError, ParameterStore

        # Test with valid comma-separated emails
        ssm.put_parameter(
            Name="/support/emails/emails",
            Type="String",
            Value="support1@example.com, support2@example.com, support3@example.com",
        )

        store = ParameterStore.create_from_environment()
        assert store

        emails = store.get_support_emails("/support/emails")
        assert emails == [
            "support1@example.com",
            "support2@example.com",
            "support3@example.com",
        ]

        # Test with single email
        ssm.put_parameter(
            Name="/support/single/emails",
            Type="String",
            Value="single@example.com",
        )

        single_email = store.get_support_emails("/support/single")
        assert single_email == ["single@example.com"]

        # Test with whitespace-only string (should raise error after stripping)
        ssm.put_parameter(Name="/support/whitespace/emails", Type="String", Value="   ")

        with pytest.raises(ParameterError, match="No valid support emails found"):
            store.get_support_emails("/support/whitespace")

        # Test with missing parameter (should raise error)
        with pytest.raises(ParameterError):
            store.get_support_emails("/support/nonexistent")
