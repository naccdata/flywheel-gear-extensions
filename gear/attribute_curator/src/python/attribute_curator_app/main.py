"""Defines Attribute Curator."""
import logging

from curator.form_curator import FormCurator
from curator.scheduling import ProjectCurationScheduler

log = logging.getLogger(__name__)


def run(curator: FormCurator, scheduler: ProjectCurationScheduler) -> None:
    """Runs the Attribute Curator process.

    Args:
        curator: FormCurator which handles the type of file
            and derive rules to curate with
        scheduler: Schedules the files to be curated
    """
    scheduler.apply(curator)
