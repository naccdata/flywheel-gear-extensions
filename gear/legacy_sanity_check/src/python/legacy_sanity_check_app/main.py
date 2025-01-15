"""Defines Legacy Sanity Check."""

import logging

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)

def run(*,
        proxy: FlywheelProxy,
        new_only: bool = False):
    """Runs the Legacy Sanity Check process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    pass
