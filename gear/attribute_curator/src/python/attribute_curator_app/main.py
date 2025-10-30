"""Defines Attribute Curator."""

import importlib.metadata
import json
import logging

from curator.form_curator import FormCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from nacc_attribute_deriver.attribute_deriver import (
    AttributeDeriver,
    MissingnessDeriver,
)

log = logging.getLogger(__name__)


def run(
    context: GearToolkitContext,
    scheduler: ProjectCurationScheduler,
    curation_tag: str,
    force_curate: bool = False,
    max_num_workers: int = 4,
) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        curation_type: which type of file and derive rules to curate with
        scheduler: Schedules the files to be curated
        curation_tag: Tag to apply to curated files
        force_curate: Curate file even if it's already been curated
        max_num_workers: Max number of workers to use
    """
    version = importlib.metadata.version("nacc_attribute_deriver")
    log.info(f"Running nacc-attribute-deriver version {version}")

    curator = FormCurator(
        attribute_deriver=AttributeDeriver(),
        missingness_deriver=MissingnessDeriver(),
        curation_tag=curation_tag,
        force_curate=force_curate
    )

    scheduler.apply(curator=curator,
                    context=context,
                    max_num_workers=max_num_workers)

    if curator.failed_files:
        failed_files = curator.failed_files.copy()
        log.error(json.dumps(failed_files, indent=4))
        raise GearExecutionError(
            f"Failed to curate {len(failed_files)} files, see above error logs"
        )
