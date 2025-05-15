"""Defines Attribute Curator."""
import json
import logging

from curator.form_curator import FormCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver

log = logging.getLogger(__name__)


def run(context: GearToolkitContext,
        deriver: AttributeDeriver,
        scheduler: ProjectCurationScheduler,
        curation_tag: str,
        force_curate: bool = False) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        deriver: attribute deriver
        curation_type: which type of file and derive rules to curate with
        scheduler: Schedules the files to be curated
        curation_tag: Tag to apply to curated files
        force_curate: Curate file even if it's already been curated
    """
    curator = FormCurator(deriver=deriver,
                          curation_tag=curation_tag,
                          force_curate=force_curate)

    scheduler.apply(curator=curator, context=context)

    if curator.failed_files:
        log.error(json.dumps(curator.failed_files, indent=4))
        raise GearExecutionError(
            f"Failed to curate {len(curator.failed_files)} files, see above error logs"
        )
