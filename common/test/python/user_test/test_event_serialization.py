"""Test UserProcessEvent serialization for CSV export."""

from datetime import datetime

from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserProcessEvent,
)


def test_user_process_event_serialization_flattens_user_context():
    """Test that model_dump() flattens user_context fields."""
    event = UserProcessEvent(
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
        message="Test message",
        action_needed="Test action",
    )

    serialized = event.model_dump()

    # Verify user_context is flattened
    assert "user_context" not in serialized
    assert serialized["email"] == "user@example.com"
    assert serialized["name"] == "John Doe"
    assert serialized["center_id"] == "42"  # Serialized as string
    assert serialized["registry_id"] == "reg-123"
    assert serialized["auth_email"] == "user@auth.com"

    # Verify other fields are present
    assert serialized["event_id"] == "test-123"
    assert serialized["timestamp"] == "2024-01-15T10:30:00"
    assert serialized["message"] == "Test message"
    assert serialized["action_needed"] == "Test action"


def test_user_process_event_serialization_with_none_values():
    """Test that model_dump() handles None values correctly."""
    event = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.MISSING_DIRECTORY_DATA,
        user_context=UserContext(
            email="user@example.com",
            name="Jane Doe",
            center_id=None,
            registry_id=None,
            auth_email=None,
        ),
        message="Test message",
        action_needed=None,
    )

    serialized = event.model_dump()

    # Verify None values are serialized as None (not empty strings)
    assert serialized["center_id"] is None
    assert serialized["registry_id"] is None
    assert serialized["auth_email"] is None
    assert serialized["action_needed"] is None


def test_user_process_event_category_serialization():
    """Test that category enum is serialized correctly."""
    event = UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.BAD_ORCID_CLAIMS,
        user_context=UserContext(
            email="user@example.com",
            name="Test User",
        ),
        message="Test",
    )

    serialized = event.model_dump()

    # Category should be serialized to human-readable value
    assert serialized["category"] == "Bad ORCID Claims"
