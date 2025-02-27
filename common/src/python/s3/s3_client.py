"""Utilities for using S3 client."""
import logging
from io import StringIO
from typing import Optional

import boto3
from botocore.config import Config
from inputs.environment import get_environment_variable
from inputs.parameter_store import S3Parameters
from keys.keys import DefaultValues

log = logging.getLogger(__name__)


class S3BucketReader:
    """Reads files from an S3 bucket."""

    def __init__(self, boto_client, bucket_name: str) -> None:
        """Creates an object that uses the boto3 client to read from the
        bucket.

        Args:
          boto_client: the boto3 s3 client
          bucket_name: the prefix for the bucket
        Returns:
          the object for the client and bucket
        """
        self.__client = boto_client
        self.__bucket = bucket_name

    @property
    def exceptions(self):
        """Expose boto client exceptions."""
        return self.__client.exceptions

    @property
    def bucket_name(self) -> str:
        """Expose name of bucket."""
        return self.__bucket

    def read_data(self, filename: str) -> StringIO:
        """Reads the file object from S3 with bucket name and file name.

        Args:
        file_name: name of file
        """

        file_obj = self.__client.get_object(Bucket=self.__bucket, Key=filename)

        return StringIO(file_obj['Body'].read().decode('utf-8'))

    def read_directory(self, prefix: str) -> dict[str, dict]:
        """Retrieve all file objects from the directory specified by the prefix
        within the S3 bucket.

        Args:
            prefix: directory prefix within the bucket
        Returns:
            Dict[str, Dict]: Set of file objects
        """

        file_objects = {}
        paginator = self.__client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
        for page in pages:
            if 'Contents' not in page:
                continue

            for s3_obj_info in page['Contents']:
                # Skip paths ending in /
                if not s3_obj_info['Key'].endswith('/'):
                    s3_obj = self.__client.get_object(Bucket=self.bucket_name,
                                                      Key=s3_obj_info['Key'])
                    if s3_obj:
                        file_objects[s3_obj_info['Key']] = s3_obj

        return file_objects

    @classmethod
    def create_from(cls,
                    parameters: S3Parameters) -> Optional['S3BucketReader']:
        """Returns the bucket reader using the access credentials in the
        parameters object.

        Args:
          parameters: dictionary of S3 parameters
        Returns:
          the S3BucketReader
        """

        client = boto3.client(
            's3',
            aws_access_key_id=parameters['accesskey'],
            aws_secret_access_key=parameters['secretkey'],
            region_name=parameters['region'],
            config=Config(
                max_pool_connections=DefaultValues.MAX_POOL_CONNECTIONS))

        return S3BucketReader(boto_client=client,
                              bucket_name=parameters['bucket'])

    @classmethod
    def create_from_environment(cls,
                                s3bucket: str) -> Optional['S3BucketReader']:
        """Returns the bucket reader using the gearbot access credentials
        stored in the environment variables. Use this method only if nacc-
        flywheel-gear user has access to the specified S3 bucket.

        Args:
          s3bucket: S3 bucket name
        Returns:
          the S3BucketReader
        """

        secret_key = get_environment_variable('AWS_SECRET_ACCESS_KEY')
        access_id = get_environment_variable('AWS_ACCESS_KEY_ID')
        region = get_environment_variable('AWS_DEFAULT_REGION')

        client = boto3.client(
            's3',
            aws_access_key_id=access_id,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                max_pool_connections=DefaultValues.MAX_POOL_CONNECTIONS))

        return S3BucketReader(boto_client=client, bucket_name=s3bucket)
