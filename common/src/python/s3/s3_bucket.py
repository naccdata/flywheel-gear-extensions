"""Utilities for using S3 client."""

import fnmatch
import logging
import re
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from inputs.environment import get_environment_variable
from inputs.parameter_store import S3Parameters
from keys.keys import DefaultValues

log = logging.getLogger(__name__)

S3_PATH_RE = re.compile(
    r"^(?P<bucket>[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?)/"
    r"(?P<key>[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)$"
)


class S3InterfaceError(Exception):
    pass


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
        # ensure the bucket exists
        try:
            boto_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            raise S3InterfaceError(f"Bucket {bucket_name} does not exist: {e}") from e

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
        log.info(f"Uploading results to: {self.__bucket}/{output_prefix}")

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

    def upload_file(
        self, local_file: Path, output_prefix: str, relative_path: Optional[str] = None
    ) -> None:
        """Upload a single file to the S3 bucket.

        Args:
            local_file: Local file path to upload
            output_prefix: Path prefix in storage where file will be written
            relative_path: Optional relative path to preserve subdirectory structure.
                         If not provided, uses just the filename.
        """
        if not local_file.exists() or not local_file.is_file():
            raise S3InterfaceError(
                f"{local_file} does not exist or is not a file; cannot upload"
            )

        # Use relative path if provided, otherwise just the filename
        file_path = relative_path if relative_path else local_file.name
        remote_path = f"{output_prefix}/{file_path}"

        log.debug(f"Uploading {file_path} to {remote_path}")

        try:
            self.__client.upload_file(
                Filename=str(local_file), Bucket=self.__bucket, Key=remote_path
            )
        except Exception as e:
            raise S3InterfaceError(
                f"Failed to upload '{local_file}' to {self.__bucket}/{remote_path}: {e}"
            ) from e

    def read_data(self, filename: str) -> StringIO:
        """Reads the file object from S3 with bucket name and file name.

        Args:
            filename: name of file
        """

        file_obj = self.get_file_object(filename)
        return StringIO(file_obj["Body"].read().decode("utf-8"))

    def read_directory(self, prefix: str) -> Dict[str, Dict]:
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

    def list_directory(self, prefix: str, glob: Optional[str] = None) -> List[str]:
        """Lists the directory.

        Args:
            prefix: directory prefix within bucket
            glob: Glob to filter by, if specified
        Returns:
            List of found files
        """
        found_keys = []
        paginator = self.__client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
        for page in pages:
            if "Contents" not in page:
                continue

            for s3_obj_info in page["Contents"]:
                key = s3_obj_info["Key"]

                # skip paths ending in /
                if not key.endswith("/"):
                    # skip path if it does not match the glob
                    if glob and not fnmatch.fnmatch(key, glob):
                        continue

                    found_keys.append(key)

        with_glob_str = f" with glob '{glob}'" if glob else ""
        if not found_keys:
            log.debug(f"No files found under {self.__bucket}/{prefix}{with_glob_str}")
        else:
            log.debug(
                f"Found {len(found_keys)} files under {self.__bucket}/"
                + f"{prefix}{with_glob_str}"
            )

        return found_keys

    def download_file(self, key: str, target_path: Path) -> None:
        """Downloads file to specified location.

        Args:
            key: Key within bucket of file to download
            target_path: Target location to download file to
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.__client.download_file(self.__bucket, key, target_path)
        except Exception as e:
            raise S3InterfaceError(
                f"Failed to download {self.__bucket}/{key}: {e}"
            ) from e

    def download_files(
        self, prefix: str, target_dir: Path, glob: Optional[str] = None
    ) -> None:
        """Download files from the prefix to the target directory. Preserves S3
        hierarchy under prefix.

        Args:
            prefix: Prefix within bucket to download files from
            target_dir: Target directory to download files to
            glob: Glob to filter by, if specified
        """
        # read directory and filter based on the glob
        found_files = self.list_directory(prefix, glob)

        if not found_files:
            return

        # download files; this may be inefficient if downloading a lot of files
        # since it's done one by one
        for key in found_files:
            # create relative path to preserve S3 hierarchy
            relative_path = Path(key).relative_to(prefix)
            self.download_file(key, target_dir / relative_path)

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
    def parse_bucket_and_key(self, s3_uri: str) -> Tuple[str, str]:
        """Parses the bucket and key from an S3 URI.

        Args:
            s3_uri: S3 URI to parse
        Returns:
            bucket and key, if found, None othewise
        """
        stripped_s3_file = s3_uri.strip().replace("s3://", "").rstrip("/")
        if not stripped_s3_file:
            raise S3InterfaceError(f"{s3_uri} not a valid S3 path")

        match = S3_PATH_RE.fullmatch(stripped_s3_file)
        if not match:
            raise S3InterfaceError(f"{s3_uri} not a valid S3 path")

        return (match.group("bucket"), match.group("key"))
