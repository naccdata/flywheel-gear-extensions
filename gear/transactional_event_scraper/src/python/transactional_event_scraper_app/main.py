"""Defines Transactional Event Scraper."""

import logging

from transactional_event_scraper_app.event_scraper import EventScraper
from transactional_event_scraper_app.models import ProcessingStatistics

log = logging.getLogger(__name__)


def run(*, scraper: EventScraper) -> ProcessingStatistics:
    """Runs the Transactional Event Scraper process.

    Args:
        scraper: The configured EventScraper instance

    Returns:
        ProcessingStatistics with summary of the operation

    Raises:
        GearExecutionError: If the scraping process fails
    """
    results = scraper.scrape_events()

    log.info(f"Scraping completed: {results}")
    return results
