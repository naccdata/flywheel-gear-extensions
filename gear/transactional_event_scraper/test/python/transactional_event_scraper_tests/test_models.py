"""Test the data models for the Transactional Event Scraper."""

from datetime import datetime

import pytest
from event_capture.models import DateRange
from transactional_event_scraper_app.config import TransactionalEventScraperConfig


def test_date_range_includes_file():
    """Test DateRange file inclusion logic."""
    # Test with no date restrictions
    date_range = DateRange()
    test_time = datetime(2024, 6, 15, 10, 30)
    assert date_range.includes_file(test_time) is True

    # Test with start date only
    start_date = datetime(2024, 6, 1)
    date_range = DateRange(start_date=start_date)

    assert date_range.includes_file(datetime(2024, 5, 31)) is False
    assert date_range.includes_file(datetime(2024, 6, 1)) is True
    assert date_range.includes_file(datetime(2024, 6, 15)) is True

    # Test with end date only
    end_date = datetime(2024, 6, 30)
    date_range = DateRange(end_date=end_date)

    assert date_range.includes_file(datetime(2024, 6, 15)) is True
    assert date_range.includes_file(datetime(2024, 6, 30)) is True
    assert date_range.includes_file(datetime(2024, 7, 1)) is False

    # Test with both start and end dates
    date_range = DateRange(start_date=start_date, end_date=end_date)

    assert date_range.includes_file(datetime(2024, 5, 31)) is False
    assert date_range.includes_file(datetime(2024, 6, 15)) is True
    assert date_range.includes_file(datetime(2024, 7, 1)) is False


def test_config_creation():
    """Test TransactionalEventScraperConfig creation."""
    config = TransactionalEventScraperConfig()
    assert config.dry_run is False
    assert config.event_bucket == "nacc-transaction-log"
    assert config.event_environment == "prod"
    assert config.start_date is None
    assert config.end_date is None
    assert config.apikey_path_prefix == "/prod/flywheel/gearbot"


def test_config_with_dates():
    """Test TransactionalEventScraperConfig with date values."""
    config = TransactionalEventScraperConfig(
        start_date="2024-01-01", end_date="2024-12-31"
    )
    assert config.start_date == "2024-01-01"
    assert config.end_date == "2024-12-31"


def test_config_invalid_date_format():
    """Test TransactionalEventScraperConfig with invalid date format."""
    with pytest.raises(ValueError, match="Date must be in YYYY-MM-DD format"):
        TransactionalEventScraperConfig(start_date="01/01/2024")

    # Test another invalid format
    with pytest.raises(ValueError, match="Date must be in YYYY-MM-DD format"):
        TransactionalEventScraperConfig(end_date="invalid-date")


def test_config_get_date_range():
    """Test TransactionalEventScraperConfig get_date_range method."""
    # Test with no dates
    config = TransactionalEventScraperConfig()
    assert config.get_date_range() is None

    # Test with start date only
    config = TransactionalEventScraperConfig(start_date="2024-01-01")
    date_range = config.get_date_range()
    assert date_range is not None
    assert date_range.start_date == datetime(2024, 1, 1)
    assert date_range.end_date is None

    # Test with end date only
    config = TransactionalEventScraperConfig(end_date="2024-12-31")
    date_range = config.get_date_range()
    assert date_range is not None
    assert date_range.start_date is None
    assert date_range.end_date == datetime(2024, 12, 31, 23, 59, 59)

    # Test with both dates
    config = TransactionalEventScraperConfig(
        start_date="2024-01-01", end_date="2024-12-31"
    )
    date_range = config.get_date_range()
    assert date_range is not None
    assert date_range.start_date == datetime(2024, 1, 1)
    assert date_range.end_date == datetime(2024, 12, 31, 23, 59, 59)
