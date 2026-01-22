"""Utilities for using S3 client."""

import logging
from io import StringIO
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.config import Config
from inputs.environment import get_environment_variable
from inputs.parameter_store import S3Parameters
from keys.keys import DefaultValues

log = logging.getLogger(__name__)


class S3BucketInterface:
    """Read/Write files from/to an S3 bucket."""

    def __init__(self, boto_client, bucket_name: str) -> None:
        """Creates the bucket interface object that uses the boto3 client for
        read from/write to the bucket.

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

    def get_file_object(self, filename: str) -> Dict[str, Any]:
        """Get the file object.

        Args:
            filename: name of file
        """
        return self.__client.get_object(Bucket=self.__bucket, Key=filename)

    def put_file_object(self, *, filename: str, contents: str) -> None:
        """Write the contents to the bucket with the filename.

        Args:
          contents: the file contents
          filename: the filename
        """
        self.__client.put_object(Bucket=self.__bucket, Key=filename, Body=contents)

    def upload_directory(
        self,
        local_dir: Path,
        output_prefix: str,
        exclude_patterns: Optional[List[str]] = None,
    ) -> None:
        """Upload local directory to S3.

        Args:
            local_dir: Local directory containing files to upload
            output_prefix: Path prefix under bucket where results will be written
            exclude_patterns: Optional list of glob patterns to exclude from upload
        """
        log.info(f"Uploading results to: {output_prefix}")

        if not local_dir.exists():
            raise S3InterfaceError(f"Local directory does not exist: {local_dir}")

        exclude_patterns = exclude_patterns or []

        # Find all files to upload
        files_to_upload = []
        for file_path in local_dir.rglob("*"):
            if file_path.is_file():
                # Check if file matches any exclude pattern
                should_exclude = any(
                    file_path.match(pattern) for pattern in exclude_patterns
                )
                if not should_exclude:
                    files_to_upload.append(file_path)

        if not files_to_upload:
            log.warning(f"No files found to upload in: {local_dir}")
            return

        log.info(f"Uploading {len(files_to_upload)} files")

        # Upload each file using upload_file method
        for local_file_path in files_to_upload:
            relative_path = str(local_file_path.relative_to(local_dir))
            self.upload_file(local_file_path, output_prefix, relative_path)

        log.info("Results uploaded successfully")

    def read_data(self, filename: str) -> StringIO:
        """Reads the file object from S3 with bucket name and file name.

        Args:
            filename: name of file
        """

        file_obj = self.get_file_object(filename)
        return StringIO(file_obj["Body"].read().decode("utf-8"))

    def read_directory(self, prefix: str) -> dict[str, dict]:
        """Retrieve all file objects from the directory specified by the prefix
        within the S3 bucket.

        Args:
            prefix: directory prefix within the bucket
        Returns:
            Dict[str, Dict]: Set of file objects
        """

        file_objects = {}
        paginator = self.__client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
        for page in pages:
            if "Contents" not in page:
                continue

            for s3_obj_info in page["Contents"]:
                # Skip paths ending in /
                if not s3_obj_info["Key"].endswith("/"):
                    s3_obj = self.__client.get_object(
                        Bucket=self.bucket_name, Key=s3_obj_info["Key"]
                    )
                    if s3_obj:
                        file_objects[s3_obj_info["Key"]] = s3_obj

        return file_objects

    @classmethod
    def create_from(cls, parameters: S3Parameters) -> Optional["S3BucketInterface"]:
        """Returns the bucket reader using the access credentials in the
        parameters object.

        Args:
          parameters: dictionary of S3 parameters
        Returns:
          the S3BucketInterface
        """

        client = boto3.client(
            "s3",  # type: ignore
            aws_access_key_id=parameters["accesskey"],
            aws_secret_access_key=parameters["secretkey"],
            region_name=parameters["region"],
            config=Config(max_pool_connections=DefaultValues.MAX_POOL_CONNECTIONS),
        )

        return S3BucketInterface(boto_client=client, bucket_name=parameters["bucket"])

    @classmethod
    def create_from_environment(cls, s3bucket: str) -> "S3BucketInterface":
        """Returns the bucket reader using the gearbot access credentials
        stored in the environment variables. Use this method only if nacc-
        flywheel-gear user has access to the specified S3 bucket.

        Args:
          s3bucket: S3 bucket name
        Returns:
          the S3BucketInterface
        """

        secret_key = get_environment_variable("AWS_SECRET_ACCESS_KEY")
        access_id = get_environment_variable("AWS_ACCESS_KEY_ID")
        region = get_environment_variable("AWS_DEFAULT_REGION")

        client = boto3.client(
            "s3",
            aws_access_key_id=access_id,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(max_pool_connections=DefaultValues.MAX_POOL_CONNECTIONS),
        )

        return S3BucketInterface(boto_client=client, bucket_name=s3bucket)

    @classmethod
    def parse_bucket_and_key(self, s3_uri: str) -> Tuple[str, str | None]:
        """Parses the bucket and key from an S3 URI.

        Args:
            s3_uri: S3 URI to parse
        Returns:
            bucket, key. Bucket is always expected, key not always
        """
        stripped_s3_file = s3_uri.strip().replace("s3://", "")
        s3_parts = stripped_s3_file.split("/")

        if len(s3_parts) < 2:
            return s3_parts[0], None

        return s3_parts[0], "/".join(s3_parts[1:])
