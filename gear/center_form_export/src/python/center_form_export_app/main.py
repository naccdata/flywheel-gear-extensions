"""Core business logic for Center Form Export."""

import logging
from typing import Callable, Optional

from data_requests.data_request import ModuleDataGatherer

log = logging.getLogger(__name__)


def run(
    *,
    subject_ids: list[str],
    gatherers: list[ModuleDataGatherer],
    on_module_gathered: Optional[Callable[[ModuleDataGatherer], None]] = None,
    batch_size: Optional[int] = None,
    reload_workers: Optional[int] = None,
) -> bool:
    """Gathers form data for the project's subjects across all configured
    modules.

    Applies each gatherer to the project's subjects, batching subjects per
    query rather than issuing one query per subject or one unscoped query
    for the whole project.

    Args:
        subject_ids: Flywheel subject ids in the project
        gatherers: ModuleDataGatherer instances for configured modules
        on_module_gathered: optional callback invoked with each gatherer
          immediately after its data has been gathered, before moving on
          to the next module -- e.g. to write that module's output to
          disk right away, so a later module's failure doesn't discard
          already-completed modules' output. If the callback raises, the
          exception propagates (this function does not catch it).
        batch_size: override for ModuleDataGatherer.gather_project_data's
          own batch_size default; left as-is (None) uses that default.
        reload_workers: override for
          ModuleDataGatherer.gather_project_data's own reload_workers
          default; left as-is (None) uses that default.

    Returns:
        True if processing completed (even with individual failures)
    """
    gather_kwargs = {}
    if batch_size is not None:
        gather_kwargs["batch_size"] = batch_size
    if reload_workers is not None:
        gather_kwargs["reload_workers"] = reload_workers

    total = len(gatherers)
    for index, gatherer in enumerate(gatherers, start=1):
        log.info("Gathering module %s (%d/%d)", gatherer.module_name, index, total)
        gatherer.gather_project_data(subject_ids, **gather_kwargs)
        if on_module_gathered:
            on_module_gathered(gatherer)

    return True
