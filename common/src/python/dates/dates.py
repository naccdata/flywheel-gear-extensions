"""Utility functions for converting datetime values."""
import re
from datetime import datetime

import pytz


def datetime_from_form_date(date_string: str) -> datetime:
    """Converts date string to datetime based on format.

    Expects either `%Y-%m-%d` or `%m/%d/%Y`.

    Args:
      date_string: the date string
    Returns:
      the date as datetime
    """
    if re.match(r"\d{4}-\d{2}-\d{2}", date_string):
        return datetime.strptime(date_string, "%Y-%m-%d")

    return datetime.strptime(date_string, "%m/%d/%Y")


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
