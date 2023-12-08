"""Tests for parameter store class.

Note: ParameterStore uses boto3 and these tests use moto for mocking.
Moto documentation says imports of boto3 need to occur within scope
where the mock is enabled.
So, imports of ParameterStore are done within tests.
"""
import os

import boto3
import pytest
from moto import mock_ssm
from typing_extensions import TypedDict


@pytest.fixture(scope="function")
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ['AWS_SECRET_ACCESS_KEY'] = "testing"
    os.environ['AWS_ACCESS_KEY_ID'] = "testing"
    os.environ['AWS_DEFAULT_REGION'] = "us-east-1"


@pytest.fixture(scope="function")
def ssm(aws_credentials):
    with mock_ssm():
        yield boto3.client('ssm', region_name="us-east-1")


class TestParameters(TypedDict):
    param1: str
    param2: str


@mock_ssm
class TestParameterStore:
    """Tests for parameter store class."""

    def test_empty(self, aws_credentials):
        from inputs.parameter_store import ParameterError, ParameterStore

        store = ParameterStore.create_from_environment()
        assert store

        # TODO: check error message
        with pytest.raises(ParameterError):
            store.get_api_key()

    def test_api_key(self, ssm):
        from inputs.parameter_store import ParameterStore

        ssm.put_parameter(Name='/prod/flywheel/gearbot/apikey',
                          Type='SecureString',
                          Value='dummy')  # type: ignore

        store = ParameterStore.create_from_environment()
        assert store

        value = store.get_api_key()
        assert value == 'dummy'

    def test_dict_parameters(self, ssm):
        from inputs.parameter_store import ParameterError, ParameterStore

        ssm.put_parameter(Name='/test/valid/param1', Type='String', Value='1')
        ssm.put_parameter(Name='/test/valid/param2', Type='String', Value='2')
        ssm.put_parameter(Name='/test/invalid/nonparam1',
                          Type='String',
                          Value='one')

        store = ParameterStore.create_from_environment()
        assert store

        # NOTE: type parameter must be a subtype of typing_extensions.TypeDict
        valid_parameters = store.get_parameters(param_type=TestParameters,
                                                parameter_path='/test/valid')
        assert valid_parameters
        assert list(valid_parameters.keys()) == ['param1', 'param2']

        # TODO: check error message
        with pytest.raises(ParameterError):
            store.get_parameters(param_type=TestParameters,
                                 parameter_path='/test/invalid')
