"""Defines Gather Form Data."""

import logging
from csv import DictWriter
from typing import Sequence

from data_requests.data_request import (
    DataRequestMatch,
)
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from keys.types import ModuleName
from outputs.error_writer import ErrorWriter

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    module_name: ModuleName,
    data_requests: Sequence[DataRequestMatch],
    writer: DictWriter,
    error_writer: ErrorWriter,
):
    """Runs the Gather Form Data process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    for request in data_requests:
        files = proxy.get_files(
            f"parent_ref.type=acquisition,parents.subject={request.subject_id},"
            f"acquisition.label={module_name}"
        )
