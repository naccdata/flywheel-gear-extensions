"""Defines UDS Curator."""

import logging

from curator.scheduling import ProjectCurationError, ProjectFormCurator
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit.context.context import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError

from uds_curator_app.uds_curator import UDSFileCurator

log = logging.getLogger(__name__)


def run(*, context: GearToolkitContext, project: ProjectAdaptor) -> None:
    """Runs the UDS Curator process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    try:
        curator = ProjectFormCurator.create(project=project)
    except ProjectCurationError as error:
        raise GearExecutionError(error) from error

    curator.apply(context=context, curator_type=UDSFileCurator)
