"""Defines Form Deletion."""

import logging

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from submissions.models import DeleteRequest

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    project: ProjectAdaptor,
    delete_request: DeleteRequest,
    module_configs: ModuleConfigs,
):
    """Runs the Form Deletion process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    pass
