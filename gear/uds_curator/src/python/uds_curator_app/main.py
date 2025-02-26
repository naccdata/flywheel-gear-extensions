"""Defines UDS Curator."""

import logging
from typing import Any, Dict

from flywheel.models.file_entry import FileEntry
from flywheel_gear_toolkit.context.context import GearToolkitContext

from uds_curator_app.uds_curator import UDSFileCurator

log = logging.getLogger(__name__)


def run(*, context: GearToolkitContext, input_file: Dict[str, Any]) -> None:
    """Runs the UDS Curator process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    curator = UDSFileCurator(context=context, write_report=False)
    curator.curate_file(input_file)
