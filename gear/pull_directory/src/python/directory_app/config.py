"""Configuration handling for the pull-directory gear."""

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

# REDCap server timezone — PHP is configured with
# date.timezone = America/Los_Angeles
REDCAP_SERVER_TIMEZONE = ZoneInfo("America/Los_Angeles")


class TimeWindowConfig(BaseModel):
    """Configuration model for the preceding time window."""

    threshold: float = Field(
        default=0,
        description=("Hours to look back for modified records. 0 = full pull."),
    )

    @field_validator("threshold")
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        """Validate threshold is not negative."""
        if value < 0:
            raise ValueError("threshold must be non-negative")
        return value

    def get_date_range_begin(self, now: Optional[datetime] = None) -> Optional[str]:
        """Compute dateRangeBegin in REDCap server time, or None if no
        filtering.

        Returns only the begin timestamp. The end is intentionally omitted
        so that REDCap uses its own server time as the upper bound.

        The timestamp is computed in America/Los_Angeles (Pacific) to match
        the REDCap server's PHP timezone configuration.

        Args:
            now: Reference time for computing the range. Defaults to the
                current time in the REDCap server timezone.

        Returns:
            The begin timestamp formatted as "YYYY-MM-DD HH:MM:SS" in
            REDCap server time, or None when threshold is 0 (full pull).
        """
        if self.threshold == 0:
            return None

        if now is None:
            now = datetime.now(REDCAP_SERVER_TIMEZONE)

        begin = now - timedelta(hours=self.threshold)
        return begin.strftime("%Y-%m-%d %H:%M:%S")
