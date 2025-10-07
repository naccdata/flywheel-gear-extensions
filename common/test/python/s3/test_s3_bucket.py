import os
import boto3
from moto import mock_aws
import pytest

from s3.s3_bucket import S3BucketInterface


@pytest.fixture(scope="function")
def aws_credentials():
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

@pytest.fixture
def fake_s3(aws_credentials):
    with mock_aws():
        yield None

@pytest.fixture
def testing_bucket(fake_s3) -> S3BucketInterface:
    bucket_name = "test_event_logging"

    s3_client = boto3.client("s3")
    s3_client.create_bucket(Bucket=bucket_name)

    return S3BucketInterface(boto_client=s3_client, bucket_name=bucket_name)

class TestS3BucketInterface:

    def test_empty(self, testing_bucket):
        assert False
