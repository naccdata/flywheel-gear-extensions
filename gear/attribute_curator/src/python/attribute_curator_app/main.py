"""Defines Attribute Curator."""
import logging

from curator.form_curator import CurationType, FormCurator, UDSFormCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver

log = logging.getLogger(__name__)


def run(context: GearToolkitContext, deriver: AttributeDeriver,
        scheduler: ProjectCurationScheduler) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        deriver: attribute deriver
        curation_type: which type of file and derive rules to curate with
        scheduler: Schedules the files to be curated
    """

    scheduler.apply(context=context, curator_type=FormCurator, deriver=deriver)
