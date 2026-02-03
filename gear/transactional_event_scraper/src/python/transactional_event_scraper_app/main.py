"""Defines Transactional Event Scraper."""

import logging

from transactional_event_scraper_app.event_scraper import EventScraper

log = logging.getLogger(__name__)


def run(*, scraper: EventScraper) -> None:
    """Runs the Transactional Event Scraper process.

    Args:
        scraper: The configured EventScraper instance

    Raises:
        GearExecutionError: If the scraping process fails
    """
    scraper.scrape_events()

    log.info("Scraping completed")
