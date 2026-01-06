"""Defines DBT Runner."""

import logging

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


def run(*, proxy: FlywheelProxy):
    """Runs the DBT Runner process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    pass
