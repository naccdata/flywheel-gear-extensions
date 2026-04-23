"""Property-based tests for TimeWindowConfig.

Feature: pull-directory-date-range
"""

from datetime import datetime, timedelta

import pytest
from directory_app.config import TimeWindowConfig
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError


class TestNonNegativeValidation:
    """Property 1: Non-negative validation accepts if and only if non-negative.

    For any numeric value, TimeWindowConfig(threshold=value) succeeds
    if and only if the value is non-negative (>= 0). Negative values must
    raise a ValidationError.

    Feature: pull-directory-date-range, Property 1
    Validates: Requirements 2.1, 2.2, 5.2
    """

    @given(
        value=st.floats(
            min_value=0.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_non_negative_values_accepted(self, value: float) -> None:
        """Non-negative floats construct successfully.

        **Validates: Requirements 2.1, 5.2**
        """
        config = TimeWindowConfig(threshold=value)
        assert config.threshold == value

    @given(
        value=st.floats(
            max_value=-1e-10,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_negative_values_rejected(self, value: float) -> None:
        """Negative floats raise ValidationError.

        **Validates: Requirements 2.2, 5.2**
        """
        with pytest.raises(ValidationError):
            TimeWindowConfig(threshold=value)


class TestDateRangeComputation:
    """Property 2: Date range computation correctness.

    For any positive preceding_hours value and any reference datetime now,
    TimeWindowConfig(threshold=value).get_date_range(now) returns a tuple
    (begin, end) where begin equals (now - timedelta(hours=value)).strftime(...)
    and end equals now.strftime(...). When preceding_hours is 0, returns None.

    Feature: pull-directory-date-range, Property 2
    Validates: Requirements 3.1, 3.2, 5.3
    """

    @given(
        value=st.floats(
            min_value=0.001,
            max_value=1e6,
            allow_nan=False,
            allow_infinity=False,
        ),
        now=st.datetimes(
            min_value=datetime(1900, 1, 1),
            max_value=datetime(2200, 1, 1),
        ),
    )
    @settings(max_examples=200)
    def test_date_range_computation_correctness(
        self,
        value: float,
        now: datetime,
    ) -> None:
        """Positive preceding_hours returns correct date range tuple.

        **Validates: Requirements 3.1, 3.2, 5.3**
        """
        config = TimeWindowConfig(threshold=value)
        result = config.get_date_range(now=now)
        assert result is not None
        begin_str, end_str = result
        expected_begin = (now - timedelta(hours=value)).strftime("%Y-%m-%d %H:%M:%S")
        expected_end = now.strftime("%Y-%m-%d %H:%M:%S")
        assert begin_str == expected_begin
        assert end_str == expected_end

    def test_zero_preceding_hours_returns_none(self) -> None:
        """threshold=0 returns None (no date filtering).

        **Validates: Requirements 3.2, 5.3**
        """
        config = TimeWindowConfig(threshold=0)
        assert config.get_date_range() is None
