"""Utilities to handle dates."""

import re
from datetime import datetime
from typing import List, Optional

from dateutil import parser

DATE_FORMATS = ["%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%Y-%m-%d"]
DATE_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class DateFormatException(Exception):
    def __init__(self, formats: List[str]) -> None:
        self.formats = formats


def parse_date(*, date_string: str, formats: List[str]) -> datetime:
    """Parses the date string against the list of formats.

    Args:
      date_string: a date as a string
    Returns:
      the datetime object for the string
    Raises:
      DateFormatException if the string doesn't match either format
    """

    for date_format in formats:
        try:
            return datetime.strptime(date_string, date_format)
        except ValueError:
            pass

    raise DateFormatException(formats=formats)


def convert_date(*, date_string: str, date_format: str) -> Optional[str]:
    """Convert the date string to desired format.

    Args:
        date_string: a date as a string
        date_format: desired date format

    Returns:
        Converted date string or None if conversion failed
    """

    yearfirst = bool(re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", date_string))

    try:
        return (
            parser.parse(date_string, yearfirst=yearfirst).date().strftime(date_format)
        )
    except (ValueError, TypeError, parser.ParserError):
        return None


def build_date(*,
               year: Optional[str] = None,
               month: Optional[str] = None,
               day: Optional[str] = None) -> Optional[datetime]:
    """Build date from year, month, and day strings. If any are None,
    or cannot be converted to proper ints, return None.

    Args:
        year: The year
        month: The month
        day: The day
    Returns:
        The full datetime, if all parts are valid.
    """
    if any(x is None for x in [year, month, day]):
        return None

    # handle unknown years; month and day 88s/99s will be handled by datetime
    if year in ["8888", "9999"]:
        return None

    try:
        return datetime(int(year), int(month), int(day))  # type: ignore
    except ValueError:
        return None
