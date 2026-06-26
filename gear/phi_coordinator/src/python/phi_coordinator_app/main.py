"""Top-level orchestration for the PHI Coordinator gear.

Defines the run function that finds completed PHI reader tasks by
protocol and applies the per-task processor to each.
"""

import logging

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from reader_tasks.reader_task_client import ReaderTaskClient

from phi_coordinator_app.processor import Outcome, PHITaskProcessor

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    reader_tasks: ReaderTaskClient,
    phi_protocol_label: str,
    answer_key: str,
    found_tag: str,
    confirmed_tag: str,
    not_found_tag: str,
    coordinated_tag: str,
    reset_on_missing_data: bool,
    dry_run: bool = False,
) -> bool:
    """Runs the PHI Coordinator process.

    Args:
        proxy: the proxy for the Flywheel instance
        reader_tasks: client for reader tasks and form responses
        phi_protocol_label: label identifying the PHI reader-task protocols
        answer_key: key in the form response_data holding the yes/no answer
        found_tag: tag marking unresolved PHI detection (removed once resolved)
        confirmed_tag: tag added when the reviewer confirms PHI
        not_found_tag: tag added when the reviewer reports no PHI
        coordinated_tag: marker added to a task once processed
        reset_on_missing_data: reset tasks lacking a usable answer to Todo
        dry_run: if True, log intended changes without applying them
    Returns:
        True if all tasks processed without error, False otherwise
    """
    protocols = reader_tasks.find_protocols(phi_protocol_label)
    if not protocols:
        log.warning(
            "No reader-task protocols found with label '%s'; nothing to do",
            phi_protocol_label,
        )
        return True

    log.info(
        "Found %d PHI protocol(s) with label '%s'",
        len(protocols),
        phi_protocol_label,
    )

    processor = PHITaskProcessor(
        proxy=proxy,
        reader_tasks=reader_tasks,
        answer_key=answer_key,
        found_tag=found_tag,
        confirmed_tag=confirmed_tag,
        not_found_tag=not_found_tag,
        coordinated_tag=coordinated_tag,
        reset_on_missing_data=reset_on_missing_data,
        dry_run=dry_run,
    )

    tally = {outcome: 0 for outcome in Outcome}
    errors = 0
    for protocol in protocols:
        for task in reader_tasks.iter_unprocessed_completed_tasks(
            protocol.id, coordinated_tag
        ):
            try:
                tally[processor.resolve(task)] += 1
            except Exception as error:
                errors += 1
                log.error("Failed to process task %s: %s", task.task_id, error)

    if dry_run:
        log.info("Dry run complete; no changes were written")
    log.info(
        "PHI Coordinator summary: confirmed=%d not_found=%d reset=%d "
        "skipped=%d errors=%d",
        tally[Outcome.CONFIRMED],
        tally[Outcome.NOT_FOUND],
        tally[Outcome.RESET],
        tally[Outcome.SKIPPED],
        errors,
    )
    return errors == 0
