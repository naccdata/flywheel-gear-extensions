"""Defines DBT Runner."""

import logging
import shutil
from pathlib import Path
from typing import Dict

import pyarrow.parquet as pq
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    GearExecutionError,
    InputFileWrapper,
)
from storage.storage import StorageManager

from .dbt_runner import DBTRunner
from .storage_configs import (
    MultiStorageConfigs,
    SingleStorageConfigs,
    StorageConfigs,
)
from .validation import validate_dbt_project, validate_source_data

log = logging.getLogger(__name__)


def download_and_aggregate_sources(
    storage_manager: StorageManager,
    source_prefixes: Dict[str, str],
    aggregation_dir: Path,
    source_data_dir: Path,
) -> None:
    """Aggregate data sources.

    Args:
        storage_manager: StorageManager for downloading data
        source_prefixes: Mapping of center to source prefixes to
            pull from
        aggregation_dir: Location to initially download files before
            aggregation
        source_data_dir: Location to write final aggregation
    """
    # need to open writers for each unique table, and append as we find them
    table_writers = {}

    try:
        for center, source_prefix in source_prefixes.items():
            target_dir = aggregation_dir / center
            storage_manager.download_dataset(source_prefix, target_dir)

            # we only really care about the files under tables/
            tables_dir = target_dir / "tables"
            for table in tables_dir.iterdir():
                if not table.is_dir():
                    continue

                # assuming there is exactly one parquet for the table
                parquet_files = list(table.glob("*.parquet"))
                if len(parquet_files) != 1:
                    raise GearExecutionError(
                        "Did not find exactly one parquet "
                        + f"file for table {table.name} under {source_prefix}"
                    )

                data = pq.read_table(parquet_files[0])

                # TODO: this is a good spot to inject center info, something like
                # data.append_column("center", pa.array([center] * data.num_rows)

                if table.name not in table_writers:
                    table_writers[table.name] = pq.ParquetWriter(
                        source_data_dir
                        / "tables"
                        / table.name
                        / f"aggregate_{table.name}.parquet",
                        data.schema,
                    )

                table_writers[table.name].write_table(data)

                # clean up as we go
                shutil.rmtree(target_dir)
    except Exception as e:
        raise GearExecutionError(f"Failed to download from {source_prefix}: {e}") from e

    # make sure we close writers
    finally:
        for writer in table_writers.values():
            writer.close()


def run(
    *,
    context: GearToolkitContext,
    api_key: str,
    dbt_project_zip: InputFileWrapper,
    storage_configs: StorageConfigs,
) -> None:
    """Runs the DBT Runner process.

    Args:
        context: the gear context
        api_key: the FW API key
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

    # Step 1: Validate and extract dbt project
    log.info("[1/6] Validating and extracting dbt project")
    project_root = validate_dbt_project(dbt_project_zip, dbt_extract_dir)
    log.info(f"dbt project root: {project_root}")

    # Step 2: Initialize storage manager and verify access
    log.info("[2/6] Initializing storage client")

    storage_manager = StorageManager(api_key, storage_configs.storage_label)
    storage_configs.verify_access(storage_manager)

    # Step 3: Download source dataset
    log.info("[3/6] Downloading source dataset from external storage")
    if isinstance(storage_configs, SingleStorageConfigs):
        storage_manager.download_dataset(storage_configs.source_prefix, source_data_dir)
    elif isinstance(storage_configs, MultiStorageConfigs):
        aggregation_dir = work_dir / "aggregation"
        download_and_aggregate_sources(
            storage_manager,
            storage_configs.source_prefixes,
            aggregation_dir,
            source_data_dir,
        )
    else:
        raise GearExecutionError("Unhandled storage configs class")

    # Validate source data structure
    validate_source_data(source_data_dir)

    # Step 4: Run dbt
    dbt_runner = DBTRunner(project_root)
    log.info("[4/6] Executing dbt run")
    dbt_runner.run()

    # Step 5: Upload results to external storage
    log.info("[5/6] Uploading results to external storage")
    dbt_runner.upload_external_model_outputs(
        storage_manager, storage_configs.output_prefix
    )

    # Step 6: Save dbt artifacts as gear outputs
    log.info("[6/6] Saving dbt artifacts")
    dbt_runner.save_dbt_artifacts(Path(context.output_dir))

    log.info("\n" + "=" * 80)
    log.info("dbt Runner Gear - Completed successfully")
    log.info("=" * 80)
