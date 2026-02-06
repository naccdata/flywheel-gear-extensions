"""Defines Dataset Aggregator."""

import logging
from pathlib import Path
from typing import List

from flywheel_gear_toolkit import GearToolkitContext
from identifiers.model import IdentifiersMode
from s3.s3_bucket import S3BucketInterface
from storage.dataset import AggregateDataset

from .transfers_handler import check_for_transfers

log = logging.getLogger(__name__)


def run(
    *,
    context: GearToolkitContext,
    grouped_datasets: List[AggregateDataset],
    output_uri: str,
    identifiers_mode: IdentifiersMode,
    dry_run: bool = False,
):
    """Runs the Dataset Aggregator process.

    Args:
        context: the gear context
        grouped_datasets: Grouped datasets to aggregate
        output_uri: Output S3 URI to write aggregated results
            to
        identifiers_mode: Mode for identifiers repository
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

    s3_interface = None
    if not dry_run:
        # make sure we have access to the output location first
        bucket, prefix = S3BucketInterface.parse_bucket_and_key(output_uri)
        s3_interface = S3BucketInterface.create_from_environment(bucket)

    try:
        for aggregate in grouped_datasets:
            aggregate.download_and_aggregate(
                aggregate_dir=aggregate_dir, tmp_dir=tmp_dir, writers=table_writers
            )

    # finally block to make sure we always close handlers, even on error
    finally:
        for writer in table_writers.values():
            writer.close()

    log.info("Successfully aggregated centers")

    # check for duplicates
    log.info("Checking transfer duplicates...")
    check_for_transfers(aggregate_dir, identifiers_mode)

    # write results to S3
    if dry_run:
        log.info(f"DRY RUN: would have uploaded aggregate results to {output_uri}")
        return

    s3_interface.upload_directory(aggregate_dir, prefix)
