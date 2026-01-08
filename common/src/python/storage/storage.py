"""Storage module for interacting with Flywheel external storage."""

import logging
from pathlib import Path
from typing import List, Optional

from fw_client import FWClient
from fw_storage import Storage, create_storage_client

log = logging.getLogger(__name__)


class StorageError(Exception):
    """Exception class for external storage errors."""


class StorageManager:
    """Manages interactions with Flywheel external storage."""

    def __init__(self, api_key: str, storage_label: str):
        """Initialize storage manager.

        Args:
            api_key: Flywheel API key
            storage_label: Label of the external storage to use
        """
        self.fw_client = FWClient(api_key=api_key)
        self.storage_label = storage_label
        self.storage_client = self._initialize_storage()
        log.info("Storage client initialized successfully")

    def _initialize_storage(self) -> Storage:
        """Initialize storage client by fetching credentials from Flywheel
        API."""
        log.info(f"Initializing storage client for: {self.storage_label}")

        # Get list of available storages
        storages_response = self.fw_client.get("/xfer/storages")
        storages = [
            s
            for s in storages_response["results"]  # type: ignore
            if s["label"] == self.storage_label
        ]

        if not storages or len(storages) > 1:
            raise StorageError(
                f"Exactly one storage with label '{self.storage_label}' not found. "
                "Available storages: "
                f"{[s['label'] for s in storages_response['results']]}"  # type: ignore
            )

        storage = storages[0]
        log.info(f"Found storage: {storage['label']} (ID: {storage['_id']})")

        # Get storage credentials
        storage_creds = self.fw_client.get(f"/xfer/storage-creds/{storage['_id']}")
        storage_url = storage_creds["url"]  # type: ignore

        # Create storage client
        return create_storage_client(storage_url)

    def download_dataset(self, source_prefix: str, local_dir: Path) -> None:
        """Download Flywheel dataset from external storage to local directory.

        Args:
            source_prefix: Path prefix in storage where dataset is located
            local_dir: Local directory to download files to
        """
        log.info(f"Downloading dataset from: {source_prefix}")
        local_dir.mkdir(parents=True, exist_ok=True)

        # List all files in the source prefix
        try:
            files = list(self.storage_client.ls(source_prefix))
        except Exception as e:
            raise StorageError(f"Failed to list files at '{source_prefix}': {e}") from e

        if not files:
            raise StorageError(f"No files found at source prefix: {source_prefix}")

        log.info(f"Found {len(files)} files to download")

        # Download each file
        for file_info in files:
            # Get relative path from source prefix
            relative_path = file_info.path.replace(f"{source_prefix}/", "")
            local_file_path = local_dir / relative_path

            # Create parent directories if needed
            local_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            log.debug(f"Downloading: {relative_path}")
            try:
                with self.storage_client.get(file_info.path) as remote_file:  # noqa: SIM117
                    with open(local_file_path, "wb") as local_file:
                        local_file.write(remote_file.read())
            except Exception as e:
                raise StorageError(f"Failed to download '{file_info.path}': {e}") from e

        log.info(f"Dataset downloaded successfully to: {local_dir}")

    def upload_results(
        self,
        local_dir: Path,
        output_prefix: str,
        exclude_patterns: Optional[List[str]] = None,
    ) -> None:
        """Upload transformed results to external storage.

        Args:
            local_dir: Local directory containing files to upload
            output_prefix: Path prefix in storage where results will be written
            exclude_patterns: Optional list of glob patterns to exclude from upload
        """
        log.info(f"Uploading results to: {output_prefix}")

        if not local_dir.exists():
            raise StorageError(f"Local directory does not exist: {local_dir}")

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
        """Upload a single file to external storage.

        Args:
            local_file: Local file path to upload
            output_prefix: Path prefix in storage where file will be written
            relative_path: Optional relative path to preserve subdirectory structure.
                         If not provided, uses just the filename.
        """
        if not local_file.exists():
            raise StorageError(f"Local file does not exist: {local_file}")

        if not local_file.is_file():
            raise StorageError(f"Path is not a file: {local_file}")

        # Use relative path if provided, otherwise just the filename
        file_path = relative_path if relative_path else local_file.name
        remote_path = f"{output_prefix}/{file_path}"

        log.debug(f"Uploading {file_path} to {remote_path}")
        try:
            with open(local_file, "rb") as f:
                self.storage_client.set(remote_path, f)
            log.info(f"Uploaded: {file_path}")
        except Exception as e:
            raise StorageError(f"Failed to upload '{local_file}': {e}") from e

    def verify_access(self, prefix: str) -> bool:
        """Verify that the storage and prefix are accessible.

        Args:
            prefix: Path prefix to verify access to

        Returns:
            True if access is verified

        Raises:
            StorageError: If access verification fails
        """
        log.info(f"Verifying access to: {prefix}")

        try:
            # Try to list files at the prefix
            list(self.storage_client.ls(prefix))
            log.info("Access verified successfully")
            return True
        except Exception as e:
            raise StorageError(f"Failed to verify access to '{prefix}': {e}") from e
