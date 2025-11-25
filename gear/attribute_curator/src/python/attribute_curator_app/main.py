"""Defines Attribute Curator."""

import json
import logging
from typing import MutableMapping, Optional

from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError

from .form_curator import FormCurator

log = logging.getLogger(__name__)


def run(
    context: GearToolkitContext,
    scheduler: ProjectCurationScheduler,
    curation_tag: str,
    force_curate: bool = False,
    max_num_workers: int = 4,
    rxclass_concepts: Optional[MutableMapping] = None,
) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        scheduler: Schedules the files to be curated
        curation_tag: Tag to apply to curated files
        force_curate: Curate file even if it's already been curated
        max_num_workers: Max number of workers to use
        rxclass_concepts: RxClass concepts - uses this instead of querying
            RxNav if provided
    """
    curator = FormCurator(
        curation_tag=curation_tag,
        force_curate=force_curate,
        rxclass_concepts=rxclass_concepts,
    )

    scheduler.apply(curator=curator, context=context, max_num_workers=max_num_workers)

    if curator.failed_files:
        failed_files = curator.failed_files.copy()
        log.error(json.dumps(failed_files, indent=4))
        raise GearExecutionError(
            f"Failed to curate {len(failed_files)} files, see above error logs"
        )
