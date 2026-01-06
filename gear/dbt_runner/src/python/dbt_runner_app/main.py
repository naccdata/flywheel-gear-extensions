"""Defines DBT Runner."""

import logging

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    GearExecutionError,
    InputFileWrapper,
)
from pathlib import Path
from pydantic import BaseModel, ValidationError, field_validator
from storage.storage import StorageManager

from .zip_handler import validate_dbt_project

log = logging.getLogger(__name__)


class StorageConfigs(BaseModel):
    """Model to keep track of DBT storage configs."""
    storage_label: str
    source_prefix: str
    output_prefix: str

    @field_validator("source_prefix", "output_prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        """Ensure prefixes have no trailing backslash."""
        v = v.rstrip("/")
        if not v:
            raise ValidationError("Prefix cannot be empty")

        return v


def validate_source_data(source_dir: Path) -> None:
    """Validate that source data follows Flywheel dataset schema.

    Args:
        source_dir: Directory containing the downloaded dataset

    Raises:
        GearExecutionError: If validation fails
    """
    log.info("Validating source dataset structure")

    if not source_dir.exists():
        raise GearExecutionError(f"Source directory not found: {source_dir}")

    # Check for tables directory
    tables_dir = source_dir / "tables"
    if not tables_dir.exists() or not tables_dir.is_dir():
        raise GearExecutionError(
            "Source dataset missing 'tables/' directory. "
            "Expected Flywheel dataset schema structure."
        )

    # Check that there are parquet files in the tables directory
    parquet_files = list(tables_dir.rglob("*.parquet"))
    if not parquet_files:
        raise GearExecutionError(
            "No parquet files found in source dataset 'tables/' directory"
        )

    log.info(f"Found {len(parquet_files)} parquet files in source dataset")
    log.info("Source dataset validation successful")


def run(*,
        context: GearToolkitContext,
        client: ClientWrapper,
        dbt_project_zip: InputFileWrapper,
        storage_configs: StorageConfigs) -> None:
    """Runs the DBT Runner process.

    Args:
        context: the gear context
        client: the FW client wrapper
        dbt_project_zip: the DBT project zip
        storage_configs: the external storage configs
    """
    log.info("=" * 80)
    log.info("dbt Runner Gear - Starting execution")
    log.info("=" * 80)

    # Define working directories
    work_dir = Path(context.work_dir)
    dbt_extract_dir = work_dir / "dbt_project"
    source_data_dir = work_dir / "source_data"

    try:
        # Step 1: Validate and extract dbt project
        log.info("\n[1/6] Validating and extracting dbt project")
        project_root = validate_dbt_project(
            dbt_project_zip, dbt_extract_dir
        )
        log.info(f"dbt project root: {project_root}")

        # Step 2: Initialize storage manager and verify access
        log.info("\n[2/6] Initializing storage client")

        storage_manager = StorageManager(client, storage_configs.storage_label)
        storage_manager.verify_access(storage_configs.source_prefix)

        # Step 3: Download source dataset
        log.info("[3/7] Downloading source dataset from external storage")
        storage_manager.download_dataset(storage_configs.source_prefix, source_data_dir)

        # Validate source data structure
        validate_source_data(source_data_dir)

        # Step 4: Run dbt
        dbt_runner = DBTRunner(project_root)
        log.info("\n[4/6] Executing dbt run")
        dbt_runner.run()

        # Step 5: Upload results to external storage
        log.info("\n[5/6] Uploading results to external storage")
        dbt_runner.upload_external_model_outputs(
            storage_manager, storage_configs.output_prefix
        )

        # Step 6: Save dbt artifacts as gear outputs
        log.info("\n[6/6] Saving dbt artifacts")
        dbt_runner.save_dbt_artifacts(Path(context.output_dir))

        log.info("\n" + "=" * 80)
        log.info("dbt Runner Gear - Completed successfully")
        log.info("=" * 80)
