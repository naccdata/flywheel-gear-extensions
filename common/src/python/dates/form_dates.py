"""Utilities to handle dates."""

import re
from datetime import datetime
from typing import List, Optional

from dateutil import parser

DATE_FORMATS = ["%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d", "%Y-%m-%d"]
DATE_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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


class DateFormatException(Exception):
    def __init__(self, formats: List[str]) -> None:
        self.formats = formats
