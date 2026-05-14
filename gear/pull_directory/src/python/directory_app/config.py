"""Configuration handling for the pull-directory gear."""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from pydantic import BaseModel, Field, field_validator


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

    def get_date_range(
        self, now: Optional[datetime] = None
    ) -> Optional[Tuple[str, str]]:
        """Compute (dateRangeBegin, dateRangeEnd) or None if no filtering.

        Args:
            now: Reference time for computing the range. Defaults to
                datetime.now() if not provided.

        Returns:
            A tuple of (begin, end) formatted as "YYYY-MM-DD HH:MM:SS",
            or None when threshold is 0.
        """
        if self.threshold == 0:
            return None

        if now is None:
            now = datetime.now()

        begin = now - timedelta(hours=self.threshold)
        return (
            begin.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
        )
