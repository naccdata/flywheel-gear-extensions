"""Defines Attribute Curator."""
import logging

from curator.form_curator import FormCurator
from curator.scheduling import ProjectCurationScheduler

log = logging.getLogger(__name__)


def run(curator: FormCurator, scheduler: ProjectCurationScheduler) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: GearToolKitContext
        project: The project to be curated over
        deriver_rules: CSV file containing the derivation rules
        date_key: Date key to order data by
        filename_pattern: Filename pattern to match on
        curation_type: Whether or not this is an UDS form
    """
    scheduler.apply(curator)
