"""Defines Attribute Curator."""

import csv
import logging

from curator.scheduling import ProjectCurationScheduler
from fw_gear import GearContext

from .form_curator import FormCurator

log = logging.getLogger(__name__)


def run(
    context: GearContext,
    curator: FormCurator,
    scheduler: ProjectCurationScheduler,
    max_num_workers: int = 4,
) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        curator: The Curator object that will perform curation
        max_num_workers: Max number of workers to use
    """
    scheduler.apply(curator=curator, context=context, max_num_workers=max_num_workers)

    if curator.failed_files:
        failed_files = list(curator.failed_files)

        with context.open_output(
            "curation-failures.csv", mode="w", encoding="utf-8"
        ) as fh:
            writer = csv.DictWriter(fh, fieldnames=failed_files[0].keys())
            writer.writeheader()
            writer.writerows(failed_files)

        log.error(f"Failed to curate {len(failed_files)} files, see error logs")
