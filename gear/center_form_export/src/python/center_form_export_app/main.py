"""Core business logic for Center Form Export."""

import logging

from data_requests.data_request import (
    DataRequestMatch,
    ModuleDataError,
    ModuleDataGatherer,
)

log = logging.getLogger(__name__)


def run(
    *,
    requests: list[DataRequestMatch],
    gatherers: list[ModuleDataGatherer],
) -> bool:
    """Gathers form data for each subject across all configured modules.

    Applies each gatherer to each request. Logs warnings for data access
    failures and continues processing all subjects.

    Args:
        requests: DataRequestMatch objects for each subject
        gatherers: ModuleDataGatherer instances for configured modules

    Returns:
        True if processing completed (even with individual failures)
    """
    for request in requests:
        for gatherer in gatherers:
            try:
                gatherer.gather_request_data(request)
            except ModuleDataError as error:
                log.warning(
                    "Error gathering data for subject %s, module %s: %s",
                    request.naccid,
                    gatherer.module_name,
                    str(error),
                )

    return True
