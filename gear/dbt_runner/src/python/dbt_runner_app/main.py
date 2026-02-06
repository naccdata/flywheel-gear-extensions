"""Defines DBT Runner."""

import logging
from pathlib import Path
from typing import Dict

from fw_gear import GearContext
from gear_execution.gear_execution import (
    InputFileWrapper,
)
from s3.s3_bucket import S3BucketInterface

from .dbt_runner import DBTRunner
from .validation import validate_dbt_project, validate_source_data

log = logging.getLogger(__name__)


def run(
    *,
    context: GearContext,
    dbt_project_zip: InputFileWrapper,
    source_prefixes: Dict[str, Dict[str, str]],
    output_prefix: str,
    dry_run: bool = True,
    debug: bool = False,
) -> None:
    """Runs the DBT Runner process.

    Args:
        context: the gear context
        dbt_project_zip: the DBT project zip
        source_prefixes: the table to source prefix mappings,
            grouped by bucket
        output_prefix: The output prefix
        dry_run: whether or not this is a dry run
        debug: whether or not to run in debug mode
    """
    # parse out the output prefix bucket/key and create its
    # S3 interface
    output_bucket, output_key = S3BucketInterface.parse_bucket_and_key(output_prefix)
    output_s3_interface = S3BucketInterface.create_from_environment(output_bucket)

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

    # Step 2: Initialize S3 storage client and verify access
    log.info("[2/6] Downloading source prefixes from S3")
    for bucket, prefixes in source_prefixes.items():
        # create client from bucket and environment
        # if same as output interface, just use that
        if bucket == output_bucket:
            s3_interface = output_s3_interface
        else:
            s3_interface = S3BucketInterface.create_from_environment(bucket)

        # download .parquet files under the specified
        # prefixes under this bucket to the specified tables
        for table, prefix in prefixes.items():
            s3_interface.download_files(
                prefix, source_data_dir / table, glob="*.parquet"
            )

    log.info("[3/6] Validating source data structure")
    # Step 3: Validate source data structure
    validate_source_data(source_data_dir)

    # Step 4: Run dbt
    dbt_runner = DBTRunner(project_root)
    log.info("[4/6] Executing dbt run")
    dbt_runner.run()

    if dry_run:
        log.info("[5/6] DRY RUN: skipping uploading results to S3")
    else:
        # Step 5: Upload results to S3
        log.info("[5/6] Uploading results to S3")
        dbt_runner.upload_external_model_outputs(output_s3_interface, output_key)

    if not debug:
        log.info("[6/6] Not debugging; skipping saving dbt artifacts")
    else:
        # Step 6: Save dbt artifacts as gear outputs
        log.info("[6/6] Saving dbt artifacts")
        dbt_runner.save_dbt_artifacts(Path(context.output_dir))

    log.info("\n" + "=" * 80)
    log.info("dbt Runner Gear - Completed successfully")
    log.info("=" * 80)
