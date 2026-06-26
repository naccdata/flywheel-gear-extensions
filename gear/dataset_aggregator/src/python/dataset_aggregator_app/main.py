"""Defines Dataset Aggregator."""

import logging
import os
from pathlib import Path

from fw_gear import GearContext
from s3.s3_bucket import S3BucketInterface
from storage.dataset import AggregateDataset

from .duplicates_handler import DuplicatesHandler

log = logging.getLogger(__name__)


def run(
    *,
    context: GearContext,
    aggregate: AggregateDataset,
    output_uri: str,
    duplicates_handler: DuplicatesHandler,
    provenance_file: Path,
    dry_run: bool = False,
    etl_date: str,
    freeze_date: str,
):
    """Runs the Dataset Aggregator process.

    Args:
        context: the gear context
        aggregate: The AggregateDataset containing datasets to
            aggregate
        output_uri: Output S3 URI to write aggregated results
            to
        duplicates_handler: DuplicatesHandler
        provenance_file: File containing provenance info
        dry_run: Whether or not to do a dry run; if True,
            will not write results to S3
        etl_date: timestamp this aggregation etl was initiated
        freeze_date: Date of the freeze, in YYYYMMDD format;
            will use the ETL date (time of execution) if not
            provided
    """
    work_dir = Path(context.work_dir)
    aggregate_dir = work_dir / "aggregate"
    aggregate_dir.mkdir(parents=True, exist_ok=True)

    s3_output_interface = None
    if not dry_run:
        # make sure we have access to the output location first
        bucket, prefix = S3BucketInterface.parse_bucket_and_key(
            f"{output_uri}/{etl_date}"
        )
        s3_output_interface = S3BucketInterface.create_from_environment(bucket)

        # write provenance
        s3_output_interface.upload_file(provenance_file, prefix)

    log.info(f"Grabbing latest datasets under {aggregate.bucket}...")

    """
    Due to how large these parquets get it's better to process
    each table one at a time
        1. Aggregate data
        2. Handle duplicate transfers
        3. Upload to S3
        4. Remove local aggregate file when done
    """
    for table in aggregate.tables:
        aggregate_file = aggregate.aggregate_table(
            table,
            aggregate_dir,
            extra_columns={
                "freeze_date": freeze_date,
                "etl_date": etl_date,
            },
        )
        duplicates_handler.handle(table, aggregate_file)
        target_prefix = f"{prefix}/tables/{table}"

        # write results to S3
        if dry_run:
            log.info(
                "DRY RUN: would have uploaded aggregate results to "
                + f"{target_prefix}"
            )
        else:
            log.info(f"Uploading results to {target_prefix}")
            s3_output_interface.upload_file(  # type: ignore
                aggregate_file, f"{target_prefix}"
            )

        os.remove(aggregate_file)
