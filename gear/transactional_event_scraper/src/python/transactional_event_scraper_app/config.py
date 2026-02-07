"""Configuration handling for the Transactional Event Scraper."""

import logging
from datetime import datetime
from typing import Optional

from event_capture.models import DateRange
from fw_gear import GearContext
from gear_execution.gear_execution import GearExecutionError
from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)


class TransactionalEventScraperConfig(BaseModel):
    """Configuration model for the Transactional Event Scraper gear."""

    dry_run: bool = Field(
        default=False,
        description="Whether to perform a dry run without capturing events",
    )
    event_bucket: str = Field(
        default="nacc-transaction-log", description="S3 bucket name for event storage"
    )
    event_environment: str = Field(
        default="prod", description="Environment prefix for event storage (prod/dev)"
    )
    start_date: Optional[str] = Field(
        None, description="Start date for filtering files (YYYY-MM-DD format)"
    )
    end_date: Optional[str] = Field(
        None, description="End date for filtering files (YYYY-MM-DD format)"
    )
    apikey_path_prefix: str = Field(
        default="/prod/flywheel/gearbot",
        description="AWS parameter path prefix for API key",
    )

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        """Validate date format is YYYY-MM-DD."""
        if value is None:
            return value

        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError as e:
            raise ValueError(f"Date must be in YYYY-MM-DD format: {value}") from e

    def get_date_range(self) -> Optional[DateRange]:
        """Convert string dates to DateRange object.

        Returns:
            DateRange object if dates are provided, None otherwise
        """
        if not self.start_date and not self.end_date:
            return None

        start_datetime = None
        end_datetime = None

        if self.start_date:
            start_datetime = datetime.strptime(self.start_date, "%Y-%m-%d")

        if self.end_date:
            end_datetime = datetime.strptime(self.end_date, "%Y-%m-%d")
            # Set to end of day for inclusive filtering
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)

        return DateRange(start_date=start_datetime, end_date=end_datetime)


def parse_gear_config(context: GearContext) -> TransactionalEventScraperConfig:
    """Parse gear configuration from context.

    Args:
        context: The gear toolkit context

    Returns:
        Parsed configuration object

    Raises:
        GearExecutionError: If configuration is invalid
    """
    try:
        config_dict = context.config.opts
        log.info(f"Parsing gear configuration: {config_dict}")
        return TransactionalEventScraperConfig.model_validate(config_dict)
    except ValidationError as e:
        error_msg = f"Invalid gear configuration: {e}"
        log.error(error_msg)
        raise GearExecutionError(error_msg) from e
