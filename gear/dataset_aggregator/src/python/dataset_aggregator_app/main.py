"""Defines Dataset Aggregator."""

import logging
import os
from pathlib import Path

from fw_gear import GearContext
from identifiers.model import IdentifiersMode
from s3.s3_bucket import S3BucketInterface
from storage.dataset import AggregateDataset

from .transfers_handler import TransferDuplicateHandler

log = logging.getLogger(__name__)


def run(
    *,
    context: GearContext,
    aggregate: AggregateDataset,
    output_uri: str,
    identifiers_mode: IdentifiersMode,
    dry_run: bool = False,
):
    """Runs the Dataset Aggregator process.

    Args:
        context: the gear context
        aggregate: The AggregateDataset containing datasets to
            aggregate
        output_uri: Output S3 URI to write aggregated results
            to
        identifiers_mode: Mode for identifiers repository
        dry_run: Whether or not to do a dry run; if True,
            will not write results to S3
    """
    work_dir = Path(context.work_dir)
    aggregate_dir = work_dir / "aggregate"
    aggregate_dir.mkdir(parents=True, exist_ok=True)

    s3_output_interface = None
    if not dry_run:
        # make sure we have access to the output location first
        bucket, prefix = S3BucketInterface.parse_bucket_and_key(output_uri)
        s3_output_interface = S3BucketInterface.create_from_environment(bucket)

    transfer_handler = TransferDuplicateHandler(identifiers_mode)
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
        aggregate_file = aggregate.aggregate_table(table, aggregate_dir)
        transfer_handler.handle(aggregate_file)

        # write results to S3
        if dry_run:
            log.info(
                "DRY RUN: would have uploaded aggregate results to "
                + f"{output_uri}/{table}"
            )
        else:
            log.info(f"Uploading results to {output_uri}/{table}")
            s3_output_interface.upload_file(  # type: ignore
                aggregate_file, f"{output_uri}/{table}"
            )

        os.remove(aggregate_file)
