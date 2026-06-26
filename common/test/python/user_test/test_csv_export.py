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


def test_csv_export_end_to_end_integration():
    """Integration test for end-to-end CSV export flow.

    This test verifies:
    - CSV export works correctly with sample errors
    - CSV content matches input errors
    - All fields are present and correctly formatted
    - The format is consistent regardless of how it's used

    Validates Requirements: 1.1, 1.2, 1.3, 5.1, 5.3, 5.4
    """
    # Create collector with sample errors across different categories
    collector = UserEventCollector()

    # Error 1: Full data with all optional fields
    error1 = UserProcessEvent(
        event_id="evt-001",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="user1@example.com",
            name="John Doe",
            center_id=42,
            registry_id="reg-123",
            auth_email="user1@auth.com",
        ),
        message="User record not claimed in directory",
        action_needed="Contact user to claim record",
    )

    # Error 2: Minimal data with None optional fields
    error2 = UserProcessEvent(
        event_id="evt-002",
        timestamp=datetime(2024, 1, 15, 11, 0, 0),
        event_type=EventType.ERROR,
        category=EventCategory.MISSING_DIRECTORY_DATA,
        user_context=UserContext(
            email="user2@example.com",
            name="Jane Smith",
            center_id=None,
            registry_id=None,
            auth_email=None,
        ),
        message="Missing required directory information",
        action_needed=None,
    )

    # Error 3: Special characters
    error3 = UserProcessEvent(
        event_id="evt-003",
        timestamp=datetime(2024, 1, 15, 12, 15, 30),
        event_type=EventType.ERROR,
        category=EventCategory.FLYWHEEL_ERROR,
        user_context=UserContext(
            email="user3@example.com",
            name='User, "Special" Name',
        ),
        message='Error with comma, quotes "test", and newline\nhere',
    )

    collector.collect(error1)
    collector.collect(error2)
    collector.collect(error3)

    # Export to CSV
    csv_content = export_errors_to_csv(collector)

    # Verify CSV is valid and parseable
    reader = csv.DictReader(StringIO(csv_content))
    rows = list(reader)

    # Verify correct number of rows
    assert len(rows) == 3, "Should have 3 error rows"

    # Verify all expected columns are present
    expected_columns = [
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
    assert list(rows[0].keys()) == expected_columns, "All columns should be present"

    # Verify row 1 - full data
    assert rows[0]["email"] == "user1@example.com"
    assert rows[0]["name"] == "John Doe"
    assert rows[0]["center_id"] == "42"
    assert rows[0]["registry_id"] == "reg-123"
    assert rows[0]["auth_email"] == "user1@auth.com"
    assert rows[0]["category"] == "Unclaimed Records"
    assert rows[0]["message"] == "User record not claimed in directory"
    assert rows[0]["action_needed"] == "Contact user to claim record"
    assert rows[0]["timestamp"] == "2024-01-15T10:30:00"
    assert rows[0]["event_id"] == "evt-001"

    # Verify row 2 - None fields represented as empty strings
    assert rows[1]["email"] == "user2@example.com"
    assert rows[1]["name"] == "Jane Smith"
    assert rows[1]["center_id"] == ""
    assert rows[1]["registry_id"] == ""
    assert rows[1]["auth_email"] == ""
    assert rows[1]["category"] == "Missing Directory Data"
    assert rows[1]["message"] == "Missing required directory information"
    assert rows[1]["action_needed"] == ""
    assert rows[1]["timestamp"] == "2024-01-15T11:00:00"
    assert rows[1]["event_id"] == "evt-002"

    # Verify row 3 - special characters preserved
    assert rows[2]["email"] == "user3@example.com"
    assert rows[2]["name"] == 'User, "Special" Name'
    assert rows[2]["category"] == "Flywheel Errors"
    assert rows[2]["message"] == 'Error with comma, quotes "test", and newline\nhere'
    assert rows[2]["timestamp"] == "2024-01-15T12:15:30"
    assert rows[2]["event_id"] == "evt-003"

    # Verify timestamp format is ISO 8601
    for row in rows:
        timestamp_str = row["timestamp"]
        # Should be parseable back to datetime
        parsed_timestamp = datetime.fromisoformat(timestamp_str)
        assert isinstance(parsed_timestamp, datetime)

    # Verify category values are human-readable strings
    assert rows[0]["category"] == "Unclaimed Records"
    assert rows[1]["category"] == "Missing Directory Data"
    assert rows[2]["category"] == "Flywheel Errors"


def test_csv_format_consistency():
    """Test that CSV format is consistent regardless of collector state.

    This verifies that the same collector produces the same CSV format
    when exported multiple times, ensuring consistency across gears.

    Validates Requirement: 4.6
    """
    # Create two identical collectors
    collector1 = UserEventCollector()
    collector2 = UserEventCollector()

    # Add the same error to both
    error = UserProcessEvent(
        event_id="test-123",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="user@example.com",
            name="Test User",
            center_id=42,
        ),
        message="Test error",
    )

    collector1.collect(error)
    collector2.collect(error)

    # Export both to CSV
    csv1 = export_errors_to_csv(collector1)
    csv2 = export_errors_to_csv(collector2)

    # CSV output should be identical
    assert csv1 == csv2, "Identical collectors should produce identical CSV output"

    # Verify column order is consistent
    lines1 = csv1.split("\n")
    lines2 = csv2.split("\n")

    assert lines1[0] == lines2[0], "Header row should be identical"
    assert lines1[1] == lines2[1], "Data row should be identical"
