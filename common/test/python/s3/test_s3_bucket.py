import os

import boto3
import pytest
from moto import mock_aws
from s3.s3_bucket import S3BucketInterface


@pytest.fixture(scope="function")
def aws_credentials():
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def fake_s3(aws_credentials: None):
    with mock_aws():
        yield None


@pytest.fixture
def testing_bucket(fake_s3: None) -> S3BucketInterface:
    bucket_name = "test_bucket"

    s3_client = boto3.client("s3")
    s3_client.create_bucket(Bucket=bucket_name)

    return S3BucketInterface(boto_client=s3_client, bucket_name=bucket_name)


class TestS3BucketInterface:
    def test_empty(self, testing_bucket: S3BucketInterface):
        bucket_objects = testing_bucket.read_directory("")
        assert bucket_objects == {}

    def test_put_object(self, testing_bucket: S3BucketInterface):
        test_path = "one/two/three.txt"
        test_contents = "an,example,file\n"
        testing_bucket.put_file_object(filename=test_path, contents=test_contents)
        file_stream = testing_bucket.read_data(test_path)
        file_stream.seek(0)
        content = file_stream.getvalue()
        assert content == test_contents

        testing_bucket.put_file_object(
            filename="one/three/four.txt", contents="another,example\n"
        )
        prefix_objects = testing_bucket.read_directory("one")
        assert len(prefix_objects) == 2
