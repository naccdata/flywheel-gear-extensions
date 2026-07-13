"""Utility functions for converting datetime values."""

from datetime import datetime
from typing import List

import pytz
from nacc_common.form_dates import DATE_FORMATS, parse_date


def get_localized_timestamp(datetime_obj: datetime) -> datetime:
    """Creates a localized timestamp.

    Args:
      datetime_obj: the datetime object
    Returns:
      the datetime localized to utc
    """

    # Change timestamp hour (prevents shifting to a different date in FW UI)
    datetime_obj = datetime_obj.replace(hour=12)

    # TODO: Could add a "get site timezone" function, using site location
    timezone = pytz.utc
    return timezone.localize(datetime_obj)


def normalize_date(
    date_string: str,
    target_format: str = "%Y-%m-%d",
    input_formats: List[str] = DATE_FORMATS,
) -> str:
    """Normalize date to the specified format.

    Args:
        date_string: The raw date string
        target_format: The target format
        input_formats: List of allowed input formats for the raw date string
    Returns:
        The date string normalized to the target format
    """
    datetime_obj = parse_date(date_string=date_string, formats=input_formats)
    return datetime_obj.strftime(target_format)
