"""Defines Transactional Event Scraper."""

import logging

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError

from transactional_event_scraper_app.config import TransactionalEventScraperConfig
from transactional_event_scraper_app.models import ProcessingStatistics

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    config: TransactionalEventScraperConfig,
    dry_run: bool = False,
) -> ProcessingStatistics:
    """Runs the Transactional Event Scraper process.

    Args:
        proxy: the proxy for the Flywheel instance
        config: the gear configuration
        dry_run: whether to perform a dry run

    Returns:
        ProcessingStatistics with summary of the operation

    Raises:
        GearExecutionError: If the scraping process fails
    """
    log.info("Starting Transactional Event Scraper")
    log.info(
        f"Configuration: dry_run={config.dry_run}, "
        f"event_bucket={config.event_bucket}, "
        f"event_environment={config.event_environment}"
    )

    if config.start_date or config.end_date:
        log.info(
            f"Date filtering: start_date={config.start_date}, "
            f"end_date={config.end_date}"
        )

    try:
        # TODO: Implement the actual scraping logic
        # For now, return empty results
        results = ProcessingStatistics(
            files_processed=0,
            submission_events_created=0,
            pass_qc_events_created=0,
            errors_encountered=0,
            skipped_files=0,
        )

        log.info(f"Scraping completed: {results}")
        return results

    except Exception as e:
        error_msg = f"Transactional Event Scraper failed: {e}"
        log.error(error_msg)
        raise GearExecutionError(error_msg) from e
