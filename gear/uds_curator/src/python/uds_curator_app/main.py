"""Defines UDS Curator."""

import logging

from flywheel.models.file_entry import FileEntry
from flywheel_gear_toolkit.context.context import GearToolkitContext

from uds_curator_app.uds_curator import UDSFileCurator

log = logging.getLogger(__name__)


def run(*, context: GearToolkitContext, input_file: FileEntry) -> None:
    """Runs the UDS Curator process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    curator = UDSFileCurator(context=context)
    curator.curate_container(input_file)
