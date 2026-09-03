from datetime import date, datetime

import pytest
import pytz
from dates.dates import get_localized_timestamp, get_visit_timestamp, normalize_date
from nacc_common.form_dates import DATE_FORMATS, DateFormatException, parse_date


class TestDateParsing:
    def test_parse_form_date(self):
        formats = DATE_FORMATS

        try:
            parse_date(date_string="10/06/2024", formats=formats)
            assert True, "format should match"
        except DateFormatException as error:
            assert False, f"should be no error, got {error}"  # noqa: B011

        try:
            parse_date(date_string="2024-10-06", formats=formats)
            assert True, "format should match"
        except DateFormatException as error:
            assert False, f"should be no error, got {error}"  # noqa: B011

        try:
            parse_date(date_string="20241006", formats=formats)
            assert False, "format should not match"  # noqa: B011
        except DateFormatException as error:
            assert True, f"should be error, got {error}"


class TestDateNormalization:
    def test_normalize_date(self):
        assert normalize_date("1/26/2025", "%Y-%m-%d") == "2025-01-26"
        assert normalize_date("2026/2/4", "%Y/%m/%d") == "2026/02/04"
        assert normalize_date("2026-04-29", "%m-%d-%Y") == "04-29-2026"
        assert normalize_date("3-13-2026", "%m/%d/%Y") == "03/13/2026"

        # with hour/minute/second
        assert normalize_date("05-01-2026", "%Y%m%d%H%M%S") == "20260501000000"


class TestLocalizedTimestamp:
    def test_localized_to_noon_utc(self):
        """Timestamps are localized to noon UTC to keep the date stable in the
        Flywheel UI."""
        timestamp = get_localized_timestamp(datetime(2024, 3, 15))

        assert timestamp == datetime(2024, 3, 15, 12, 0, tzinfo=pytz.utc)
        assert timestamp.hour == 12
        assert timestamp.tzinfo is not None


class TestVisitTimestamp:
    def test_normalized_date(self):
        """Visit dates reaching the uploader are normalized to YYYY-MM-DD."""
        assert get_visit_timestamp("2024-03-15") == datetime(
            2024, 3, 15, 12, 0, tzinfo=pytz.utc
        )

    def test_date_not_shifted(self):
        """The noon offset must not move the visit to a different day."""
        timestamp = get_visit_timestamp("2024-03-15")

        assert timestamp
        assert timestamp.date() == date(2024, 3, 15)

    @pytest.mark.parametrize(
        "date_string",
        ["03/15/2024", "03-15-2024", "2024/03/15", " 2024-03-15 "],
    )
    def test_accepted_date_formats(self, date_string):
        """Any format in DATE_FORMATS resolves, surrounding whitespace
        included."""
        assert get_visit_timestamp(date_string) == datetime(
            2024, 3, 15, 12, 0, tzinfo=pytz.utc
        )

    @pytest.mark.parametrize(
        "date_string",
        [None, "", "   ", "20240315", "not-a-date", "2024-13-45"],
    )
    def test_unusable_date_returns_none(self, date_string):
        """A missing or unparseable date must not raise, the timestamp is
        supplementary information."""
        assert get_visit_timestamp(date_string) is None
