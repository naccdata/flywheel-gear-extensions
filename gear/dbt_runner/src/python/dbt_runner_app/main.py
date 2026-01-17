"""Defines DBT Runner."""

import logging
from pathlib import Path

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    InputFileWrapper,
)

from .dbt_runner import DBTRunner
from .storage_handler import (
    StorageHandler,
)
from .validation import validate_dbt_project, validate_source_data

log = logging.getLogger(__name__)


def run(
    *,
    context: GearToolkitContext,
    dbt_project_zip: InputFileWrapper,
    storage_handler: StorageHandler,
    output_prefix: str,
) -> None:
    """Runs the DBT Runner process.

    Args:
        context: the gear context
        dbt_project_zip: the DBT project zip
        storage_handler: the StorageHandler
        output_prefix: output prefix to write results to
    """
    # Define working directories
    work_dir = Path(context.work_dir)
    dbt_extract_dir = work_dir / "dbt_project"
    source_data_dir = work_dir / "source_data"

    # Step 2: Validate and extract dbt project
    log.info("[2/6] Validating and extracting dbt project")
    project_root = validate_dbt_project(dbt_project_zip, dbt_extract_dir)
    log.info(f"dbt project root: {project_root}")

    # Step 3: Download source dataset
    log.info("[3/6] Downloading source dataset from external storage")
    storage_handler.download(source_data_dir)

    # Validate source data structure
    validate_source_data(source_data_dir)

    # Step 4: Run dbt
    dbt_runner = DBTRunner(project_root)
    log.info("[4/6] Executing dbt run")
    dbt_runner.run()

    # Step 5: Upload results to external storage
    log.info("[5/6] Uploading results to external storage")
    dbt_runner.upload_external_model_outputs(
        storage_handler.storage_manager, output_prefix
    )

    # Step 6: Save dbt artifacts as gear outputs
    log.info("[6/6] Saving dbt artifacts")
    dbt_runner.save_dbt_artifacts(Path(context.output_dir))
