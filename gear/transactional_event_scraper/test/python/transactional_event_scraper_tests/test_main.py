"""Unit tests for the main run function."""

from unittest.mock import Mock

import pytest
from transactional_event_scraper_app.event_scraper import EventScraper
from transactional_event_scraper_app.main import run


@pytest.fixture
def mock_scraper():
    """Create a mock EventScraper."""
    scraper = Mock(spec=EventScraper)
    return scraper


def test_run_success(mock_scraper):
    """Test successful run of the scraper."""
    mock_scraper.scrape_events.return_value = None

    # Run the scraper
    run(scraper=mock_scraper)

    # Verify scrape_events was called
    mock_scraper.scrape_events.assert_called_once()


def test_run_scraper_exception(mock_scraper):
    """Test run handles exceptions from EventScraper."""
    # Make scraper raise an exception
    mock_scraper.scrape_events.side_effect = Exception("Scraping failed")

    with pytest.raises(Exception, match="Scraping failed"):
        run(scraper=mock_scraper)


def test_run_value_error(mock_scraper):
    """Test run handles ValueError from EventScraper."""
    # Make scraper raise a ValueError
    mock_scraper.scrape_events.side_effect = ValueError("Invalid data")

    with pytest.raises(ValueError, match="Invalid data"):
        run(scraper=mock_scraper)


def test_run_api_exception(mock_scraper):
    """Test run handles ApiException from EventScraper."""
    from flywheel.rest import ApiException

    # Make scraper raise an ApiException
    mock_scraper.scrape_events.side_effect = ApiException("API error")

    with pytest.raises(ApiException, match="API error"):
        run(scraper=mock_scraper)


def test_run_logs_project_info(mock_scraper, caplog):
    """Test that run logs completion information."""
    import logging

    caplog.set_level(logging.INFO)

    mock_scraper.scrape_events.return_value = None

    # Run the scraper
    run(scraper=mock_scraper)

    # Verify completion was logged
    assert "Scraping completed" in caplog.text
