"""Tests for timestamp parsing in form_dates."""

from datetime import datetime, timedelta, timezone

import pytest
from nacc_common.form_dates import parse_timestamp


class TestParseTimestamp:
    """Tests for parse_timestamp.

    `file.info.validated-timestamp` has two writers using two formats:
    the gears write DEFAULT_DATE_TIME_FORMAT in UTC, the issue-manager
    app writes ISO 8601 with an offset. Both must parse and compare
    against each other.
    """

    def test_default_date_time_format(self):
        """Gear-written format is read as UTC."""
        assert parse_timestamp("2026-10-07 16:45:51") == datetime(
            2026, 10, 7, 16, 45, 51, tzinfo=timezone.utc
        )

    def test_iso_format_with_offset(self):
        """issue-manager format is read as UTC."""
        assert parse_timestamp("2026-10-07T16:51:59+00:00") == datetime(
            2026, 10, 7, 16, 51, 59, tzinfo=timezone.utc
        )

    def test_iso_format_with_zulu_suffix(self):
        assert parse_timestamp("2026-10-07T16:51:59Z") == datetime(
            2026, 10, 7, 16, 51, 59, tzinfo=timezone.utc
        )

    def test_fractional_seconds(self):
        assert parse_timestamp("2026-10-07T16:51:59.123+00:00") == datetime(
            2026, 10, 7, 16, 51, 59, 123000, tzinfo=timezone.utc
        )

    def test_non_utc_offset_normalized_to_utc(self):
        """A non-UTC offset shifts to the equivalent UTC instant."""
        assert parse_timestamp("2026-10-07T12:51:59-04:00") == datetime(
            2026, 10, 7, 16, 51, 59, tzinfo=timezone.utc
        )

    def test_surrounding_whitespace_ignored(self):
        assert parse_timestamp("  2026-10-07 16:45:51\n") == datetime(
            2026, 10, 7, 16, 45, 51, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize(
        "value", [None, "", "   ", "not-a-date", "10/07/2026", "2026-13-01 00:00:00"]
    )
    def test_unparseable_returns_none(self, value):
        assert parse_timestamp(value) is None

    @pytest.mark.parametrize("value", ["2026-10-07", "20261007"])
    def test_date_only_resolves_to_midnight_utc(self, value):
        """A bare ISO date is valid input and resolves to midnight UTC."""
        assert parse_timestamp(value) == datetime(2026, 10, 7, tzinfo=timezone.utc)

    def test_result_is_timezone_aware(self):
        """Both input formats yield aware datetimes, never naive ones."""
        for value in ["2026-10-07 16:45:51", "2026-10-07T16:51:59+00:00"]:
            assert parse_timestamp(value).tzinfo is not None

    def test_mixed_formats_compare(self):
        """The comparison that crashed form-qc-coordinator.

        The LBD visit was validated via the issue-manager (ISO) after a
        trigger stamped by a gear (DEFAULT_DATE_TIME_FORMAT), so the
        trigger is outdated.
        """
        validated = parse_timestamp("2026-10-07T16:51:59+00:00")
        triggered = parse_timestamp("2026-10-07 16:45:51")

        assert validated >= triggered
        assert validated - triggered == timedelta(minutes=6, seconds=8)

    def test_mixed_formats_compare_other_direction(self):
        """A visit validated before the trigger is not outdated."""
        validated = parse_timestamp("2026-10-07T16:40:00+00:00")
        triggered = parse_timestamp("2026-10-07 16:45:51")

        assert not validated >= triggered
