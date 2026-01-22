"""Defines Dataset Aggregator."""

import logging

from typing import Any, Dict

from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


def run(*,
        proxy: FlywheelProxy,
        source_prefixes: Dict[str, Dict[str, Any]],
        output_uri: str,
        file_type: str,
        dry_run: bool = False,
    ):
    """Runs the Dataset Aggregator process.

    Args:
        proxy: the proxy for the Flywheel instance
        source_prefixes: Source prefixes, mapped
            by bucket to center to latest version prefix
        output_uri: Output S3 URI to write aggregated results
            to
        dry_run: Whether or not to do a dry run; if True,
            will not write results to S3
    """
    pass
