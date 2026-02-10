"""Tests for CSV export functionality."""

import csv
from datetime import datetime
from io import StringIO

import pytest
from users.csv_export import export_errors_to_csv
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)


def test_export_errors_to_csv_single_error():
    """Test CSV export with a single error event."""
    collector = UserEventCollector()

    error_event = UserProcessEvent(
        event_id="test-123",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="user@example.com",
            name="John Doe",
            center_id=42,
            registry_id="reg-123",
            auth_email="user@auth.com",
        ),
        message="User record not claimed in directory",
        action_needed="Contact user to claim record",
    )
    collector.collect(error_event)

    csv_output = export_errors_to_csv(collector)

    # Parse CSV to verify content
    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == 1
    row = rows[0]

    assert row["email"] == "user@example.com"
    assert row["name"] == "John Doe"
    assert row["center_id"] == "42"
    assert row["registry_id"] == "reg-123"
    assert row["auth_email"] == "user@auth.com"
    assert row["category"] == "Unclaimed Records"
    assert row["message"] == "User record not claimed in directory"
    assert row["action_needed"] == "Contact user to claim record"
    assert row["timestamp"] == "2024-01-15T10:30:00"
    assert row["event_id"] == "test-123"


def test_export_errors_to_csv_multiple_errors():
    """Test CSV export with multiple error events across categories."""
    collector = UserEventCollector()

    error1 = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="user1@example.com",
            name="User One",
        ),
        message="Error 1",
    )

    error2 = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.MISSING_DIRECTORY_DATA,
        user_context=UserContext(
            email="user2@example.com",
            name="User Two",
        ),
        message="Error 2",
    )

    collector.collect(error1)
    collector.collect(error2)

    csv_output = export_errors_to_csv(collector)

    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["email"] == "user1@example.com"
    assert rows[1]["email"] == "user2@example.com"


def test_export_errors_to_csv_empty_collector():
    """Test that exporting from empty collector raises ValueError."""
    collector = UserEventCollector()

    with pytest.raises(ValueError, match="Collector has no errors to export"):
        export_errors_to_csv(collector)


def test_export_errors_to_csv_special_characters():
    """Test CSV export handles special characters correctly."""
    collector = UserEventCollector()

    error_event = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.FLYWHEEL_ERROR,
        user_context=UserContext(
            email="user@example.com",
            name='User, "Special" Name',
        ),
        message='Error with comma, quotes "test", and newline\nhere',
    )
    collector.collect(error_event)

    csv_output = export_errors_to_csv(collector)

    # Parse CSV to verify it's valid and data is preserved
    reader = csv.DictReader(StringIO(csv_output))
    rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["name"] == 'User, "Special" Name'
    assert rows[0]["message"] == 'Error with comma, quotes "test", and newline\nhere'


def test_export_errors_to_csv_column_order():
    """Test that CSV columns are in the correct order."""
    collector = UserEventCollector()

    error_event = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="user@example.com",
            name="Test User",
        ),
        message="Test",
    )
    collector.collect(error_event)

    csv_output = export_errors_to_csv(collector)

    # Check header row
    lines = csv_output.split("\n")
    header = lines[0]

    # Get expected columns from UserProcessEvent class
    expected_columns = UserProcessEvent.csv_fieldnames()

    assert header == ",".join(expected_columns)


def test_csv_fieldnames_method():
    """Test that UserProcessEvent.csv_fieldnames() returns the correct field
    names."""
    from users.event_models import UserProcessEvent

    fieldnames = UserProcessEvent.csv_fieldnames()

    expected = [
        "email",
        "name",
        "center_id",
        "registry_id",
        "auth_email",
        "category",
        "message",
        "action_needed",
        "timestamp",
        "event_id",
    ]

    assert fieldnames == expected
