"""Defines ADD DETAIL computation."""

import logging
from typing import Any, List

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)

def run(*,
        proxy: FlywheelProxy,
        object_list: List[Any],
        new_only: bool = False):
    """Runs ADD DETAIL process.
    
    Args:
      proxy: the proxy for the Flywheel instance
    """
    pass