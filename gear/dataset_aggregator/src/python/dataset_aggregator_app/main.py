"""Defines Dataset Aggregator."""

import logging
from pathlib import Path
from typing import List

from flywheel_gear_toolkit import GearToolkitContext
from s3.s3_bucket import S3BucketInterface
from storage.dataset import AggregateDataset

log = logging.getLogger(__name__)


def run(
    *,
    context: GearToolkitContext,
    grouped_datasets: List[AggregateDataset],
    output_uri: str,
    dry_run: bool = False,
):
    """Runs the Dataset Aggregator process.

    Args:
        context: the gear context
        source_prefixes: Source prefixes, mapped
            by bucket to center to latest version prefix
        output_uri: Output S3 URI to write aggregated results
            to
        dry_run: Whether or not to do a dry run; if True,
            will not write results to S3
    """
    # aggregate per table
    table_writers = {}  # type: ignore

    work_dir = Path(context.work_dir)
    aggregate_dir = work_dir / "aggregate"
    tmp_dir = work_dir / "tmp"

    aggregate_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for aggregate in grouped_datasets:
            aggregate.download_and_aggregate(
                aggregate_dir=aggregate_dir, tmp_dir=tmp_dir, writers=table_writers
            )

    # finally block to make sure we always close handlers, even on error
    finally:
        for writer in table_writers.values():
            writer.close()

    # write results to S3
    if dry_run:
        log.info(f"DRY RUN: would have uploaded aggregate results to {output_uri}")
        return

    bucket, prefix = S3BucketInterface.parse_bucket_and_key(output_uri)
    s3_interface = S3BucketInterface.create_from_environment(bucket)
    s3_interface.upload_directory(aggregate_dir, prefix)
