"""Handles validating and opening DBT project zip file."""

import logging
import zipfile
from pathlib import Path

from gear_execution.gear_execution import (
    GearExecutionError,
    InputFileWrapper,
)

log = logging.getLogger(__name__)


def _find_dbt_project_root(extract_dir: Path) -> Path:
    """Find the root directory of the dbt project within extracted files.

    Args:
        extract_dir: Directory where zip was extracted

    Returns:
        Path to the project root containing dbt_project.yml

    Raises:
        ValidationError: If project root cannot be found
    """
    # Check if dbt_project.yml is in the extract_dir directly
    if (extract_dir / "dbt_project.yml").exists():
        return extract_dir

    # Search for dbt_project.yml in subdirectories (up to 2 levels deep)
    for yml_path in extract_dir.rglob("dbt_project.yml"):
        # Return the directory containing dbt_project.yml
        if yml_path.parent.relative_to(extract_dir).parts.__len__() <= 2:
            return yml_path.parent

    raise GearExecutionError("Could not find dbt_project.yml in extracted zip file")


def validate_dbt_project(dbt_project_zip: InputFileWrapper, extract_dir: Path) -> Path:
    """Validate and extract dbt project zip file.

    Performs the following validation steps:
    1. Validates the file is a valid zip archive
    2. Validates required files exist: dbt_project.yml and profiles.yml
    3. Validates the models/ directory is present

    Args:
        dbt_project_zip: DBT Project zip file
        extract_dir: Directory to extract the project to

    Returns:
        Path to the extracted project directory

    Raises:
        ValidationError: If validation fails at any step
    """
    log.info("Validating dbt project zip file")

    # Check if it's a valid zip file
    file_type = dbt_project_zip.validate_file_extension(accepted_extensions=["zip"])
    if not file_type:
        raise GearExecutionError(
            f"DBT project zip is not a valid zip archive: {dbt_project_zip.filename}"
        )

    # Extract the zip file
    extract_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"Extracting dbt project to: {extract_dir}")

    try:
        with zipfile.ZipFile(dbt_project_zip.filepath, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        raise GearExecutionError(f"Failed to extract zip file: {e}") from e

    # Find the project root (may be in a subdirectory)
    project_root = _find_dbt_project_root(extract_dir)

    # Validate required files exist
    required_files = ["dbt_project.yml", "profiles.yml"]
    missing_files = []

    for file_name in required_files:
        file_path = project_root / file_name
        if not file_path.exists():
            missing_files.append(file_name)

    if missing_files:
        raise GearExecutionError(
            f"dbt project missing required files: {', '.join(missing_files)}"
        )

    # Check for models directory
    models_dir = project_root / "models"
    if not models_dir.exists() or not models_dir.is_dir():
        raise GearExecutionError("dbt project missing 'models/' directory")

    log.info("dbt project validation successful")
    return project_root


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
