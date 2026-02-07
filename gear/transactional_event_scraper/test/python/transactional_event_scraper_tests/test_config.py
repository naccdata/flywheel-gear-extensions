"""Unit tests for configuration handling and manifest validation."""

from unittest.mock import Mock

import pytest
from event_capture.models import DateRange
from fw_gear import GearContext
from gear_execution.gear_execution import GearExecutionError
from pydantic import ValidationError
from transactional_event_scraper_app.config import (
    TransactionalEventScraperConfig,
    parse_gear_config,
)


class TestTransactionalEventScraperConfig:
    """Tests for TransactionalEventScraperConfig model."""

    def test_config_with_defaults(self):
        """Test configuration with default values."""
        config = TransactionalEventScraperConfig()

        assert config.dry_run is False
        assert config.event_bucket == "nacc-transaction-log"
        assert config.event_environment == "prod"
        assert config.start_date is None
        assert config.end_date is None
        assert config.apikey_path_prefix == "/prod/flywheel/gearbot"

    def test_config_with_custom_values(self):
        """Test configuration with custom values."""
        config = TransactionalEventScraperConfig(
            dry_run=True,
            event_bucket="custom-bucket",
            event_environment="dev",
            start_date="2024-01-01",
            end_date="2024-12-31",
            apikey_path_prefix="/custom/path",
        )

        assert config.dry_run is True
        assert config.event_bucket == "custom-bucket"
        assert config.event_environment == "dev"
        assert config.start_date == "2024-01-01"
        assert config.end_date == "2024-12-31"
        assert config.apikey_path_prefix == "/custom/path"

    def test_config_with_valid_date_format(self):
        """Test configuration accepts valid date format (YYYY-MM-DD)."""
        config = TransactionalEventScraperConfig(
            start_date="2024-01-15", end_date="2024-06-30"
        )

        assert config.start_date == "2024-01-15"
        assert config.end_date == "2024-06-30"

    def test_config_with_invalid_start_date_format(self):
        """Test configuration rejects invalid start_date format."""
        with pytest.raises(ValidationError) as exc_info:
            TransactionalEventScraperConfig(start_date="01/15/2024")

        assert "Date must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_config_with_invalid_end_date_format(self):
        """Test configuration rejects invalid end_date format."""
        with pytest.raises(ValidationError) as exc_info:
            TransactionalEventScraperConfig(end_date="2024-13-01")

        assert "Date must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_config_with_invalid_date_values(self):
        """Test configuration rejects invalid date values."""
        with pytest.raises(ValidationError) as exc_info:
            TransactionalEventScraperConfig(start_date="2024-02-30")

        assert "Date must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_config_with_only_start_date(self):
        """Test configuration with only start_date specified."""
        config = TransactionalEventScraperConfig(start_date="2024-01-01")

        assert config.start_date == "2024-01-01"
        assert config.end_date is None

    def test_config_with_only_end_date(self):
        """Test configuration with only end_date specified."""
        config = TransactionalEventScraperConfig(end_date="2024-12-31")

        assert config.start_date is None
        assert config.end_date == "2024-12-31"

    def test_get_date_range_with_no_dates(self):
        """Test get_date_range returns None when no dates are specified."""
        config = TransactionalEventScraperConfig()
        date_range = config.get_date_range()

        assert date_range is None

    def test_get_date_range_with_start_date_only(self):
        """Test get_date_range with only start_date."""
        config = TransactionalEventScraperConfig(start_date="2024-01-01")
        date_range = config.get_date_range()

        assert date_range is not None
        assert date_range.start_date is not None
        assert date_range.start_date.year == 2024
        assert date_range.start_date.month == 1
        assert date_range.start_date.day == 1
        assert date_range.end_date is None

    def test_get_date_range_with_end_date_only(self):
        """Test get_date_range with only end_date."""
        config = TransactionalEventScraperConfig(end_date="2024-12-31")
        date_range = config.get_date_range()

        assert date_range is not None
        assert date_range.start_date is None
        assert date_range.end_date is not None
        assert date_range.end_date.year == 2024
        assert date_range.end_date.month == 12
        assert date_range.end_date.day == 31
        # Should be set to end of day
        assert date_range.end_date.hour == 23
        assert date_range.end_date.minute == 59
        assert date_range.end_date.second == 59

    def test_get_date_range_with_both_dates(self):
        """Test get_date_range with both start and end dates."""
        config = TransactionalEventScraperConfig(
            start_date="2024-01-01", end_date="2024-12-31"
        )
        date_range = config.get_date_range()

        assert date_range is not None
        assert date_range.start_date is not None
        assert date_range.end_date is not None
        assert date_range.start_date.year == 2024
        assert date_range.start_date.month == 1
        assert date_range.end_date.year == 2024
        assert date_range.end_date.month == 12


class TestParseGearConfig:
    """Tests for parse_gear_config function."""

    def test_parse_valid_config(self):
        """Test parsing valid configuration from context."""
        context = Mock(spec=GearContext)
        # Mock the Config object structure from fw_gear
        mock_config = Mock()
        mock_config.opts = {
            "dry_run": False,
            "event_bucket": "test-bucket",
            "event_environment": "dev",
            "apikey_path_prefix": "/test/path",
        }
        context.config = mock_config

        config = parse_gear_config(context)

        assert isinstance(config, TransactionalEventScraperConfig)
        assert config.dry_run is False
        assert config.event_bucket == "test-bucket"
        assert config.event_environment == "dev"
        assert config.apikey_path_prefix == "/test/path"

    def test_parse_config_with_date_filters(self):
        """Test parsing configuration with date filters."""
        context = Mock(spec=GearContext)
        # Mock the Config object structure from fw_gear
        mock_config = Mock()
        mock_config.opts = {
            "dry_run": False,
            "event_bucket": "test-bucket",
            "event_environment": "prod",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "apikey_path_prefix": "/prod/path",
        }
        context.config = mock_config

        config = parse_gear_config(context)

        assert config.start_date == "2024-01-01"
        assert config.end_date == "2024-12-31"

    def test_parse_config_with_defaults(self):
        """Test parsing configuration uses defaults for missing values."""
        context = Mock(spec=GearContext)
        # Mock the Config object structure from fw_gear
        mock_config = Mock()
        mock_config.opts = {}
        context.config = mock_config

        config = parse_gear_config(context)

        assert config.dry_run is False
        assert config.event_bucket == "nacc-transaction-log"
        assert config.event_environment == "prod"
        assert config.apikey_path_prefix == "/prod/flywheel/gearbot"

    def test_parse_config_with_invalid_date_format(self):
        """Test parsing configuration fails with invalid date format."""
        context = Mock(spec=GearContext)
        # Mock the Config object structure from fw_gear
        mock_config = Mock()
        mock_config.opts = {
            "start_date": "01/01/2024",  # Invalid format
        }
        context.config = mock_config

        with pytest.raises(GearExecutionError) as exc_info:
            parse_gear_config(context)

        assert "Invalid gear configuration" in str(exc_info.value)

    def test_parse_config_with_invalid_date_value(self):
        """Test parsing configuration fails with invalid date value."""
        context = Mock(spec=GearContext)
        # Mock the Config object structure from fw_gear
        mock_config = Mock()
        mock_config.opts = {
            "start_date": "2024-13-01",  # Invalid month
        }
        context.config = mock_config

        with pytest.raises(GearExecutionError) as exc_info:
            parse_gear_config(context)

        assert "Invalid gear configuration" in str(exc_info.value)


class TestManifestConfigurationValidation:
    """Tests to validate manifest.json configuration options."""

    def test_manifest_dry_run_option(self):
        """Test dry_run configuration option from manifest."""
        # Test with dry_run=True
        config = TransactionalEventScraperConfig(dry_run=True)
        assert config.dry_run is True

        # Test with dry_run=False (default)
        config = TransactionalEventScraperConfig(dry_run=False)
        assert config.dry_run is False

    def test_manifest_event_bucket_option(self):
        """Test event_bucket configuration option from manifest."""
        # Test with custom bucket
        config = TransactionalEventScraperConfig(event_bucket="custom-bucket")
        assert config.event_bucket == "custom-bucket"

        # Test with default
        config = TransactionalEventScraperConfig()
        assert config.event_bucket == "nacc-transaction-log"

    def test_manifest_event_environment_option(self):
        """Test event_environment configuration option from manifest."""
        # Test with dev environment
        config = TransactionalEventScraperConfig(event_environment="dev")
        assert config.event_environment == "dev"

        # Test with prod environment (default)
        config = TransactionalEventScraperConfig(event_environment="prod")
        assert config.event_environment == "prod"

    def test_manifest_start_date_option(self):
        """Test start_date configuration option from manifest."""
        # Test with valid date
        config = TransactionalEventScraperConfig(start_date="2024-01-01")
        assert config.start_date == "2024-01-01"

        # Test optional (None)
        config = TransactionalEventScraperConfig()
        assert config.start_date is None

    def test_manifest_end_date_option(self):
        """Test end_date configuration option from manifest."""
        # Test with valid date
        config = TransactionalEventScraperConfig(end_date="2024-12-31")
        assert config.end_date == "2024-12-31"

        # Test optional (None)
        config = TransactionalEventScraperConfig()
        assert config.end_date is None

    def test_manifest_apikey_path_prefix_option(self):
        """Test apikey_path_prefix configuration option from manifest."""
        # Test with custom path
        config = TransactionalEventScraperConfig(apikey_path_prefix="/custom/path")
        assert config.apikey_path_prefix == "/custom/path"

        # Test with default
        config = TransactionalEventScraperConfig()
        assert config.apikey_path_prefix == "/prod/flywheel/gearbot"

    def test_manifest_all_options_together(self):
        """Test all manifest configuration options work together."""
        config = TransactionalEventScraperConfig(
            dry_run=True,
            event_bucket="test-bucket",
            event_environment="dev",
            start_date="2024-01-01",
            end_date="2024-12-31",
            apikey_path_prefix="/test/path",
        )

        assert config.dry_run is True
        assert config.event_bucket == "test-bucket"
        assert config.event_environment == "dev"
        assert config.start_date == "2024-01-01"
        assert config.end_date == "2024-12-31"
        assert config.apikey_path_prefix == "/test/path"

    def test_manifest_date_range_filtering(self):
        """Test date range filtering works with manifest options."""
        config = TransactionalEventScraperConfig(
            start_date="2024-01-01", end_date="2024-12-31"
        )
        date_range = config.get_date_range()

        assert date_range is not None
        assert isinstance(date_range, DateRange)

        # Test that date range can filter files
        from datetime import datetime

        # File within range
        file_date = datetime(2024, 6, 15)
        assert date_range.includes_file(file_date) is True

        # File before range
        file_date = datetime(2023, 12, 31)
        assert date_range.includes_file(file_date) is False

        # File after range
        file_date = datetime(2025, 1, 1)
        assert date_range.includes_file(file_date) is False
