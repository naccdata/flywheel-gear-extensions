"""Tests for user error models (TDD)."""

import json
import uuid
from datetime import datetime
from enum import Enum

import pytest
from users.user_entry import ActiveUserEntry, PersonName, RegisteredUserEntry


class TestErrorCategory:
    """Tests for ErrorCategory enum values."""

    def test_error_category_enum_values(self):
        """Test that ErrorCategory enum has all required values."""
        # Import will be available after implementation
        from users.error_models import ErrorCategory

        # Test all required category values exist
        assert ErrorCategory.UNCLAIMED_RECORDS.value == "Unclaimed Records"
        assert ErrorCategory.EMAIL_MISMATCH.value == "Authentication Email Mismatch"
        assert ErrorCategory.UNVERIFIED_EMAIL.value == "Unverified Email"
        assert ErrorCategory.BAD_ORCID_CLAIMS.value == "Bad ORCID Claims"
        assert (
            ErrorCategory.MISSING_DIRECTORY_PERMISSIONS.value
            == "Missing Directory Permissions"
        )
        assert (
            ErrorCategory.INSUFFICIENT_PERMISSIONS.value == "Insufficient Permissions"
        )
        assert (
            ErrorCategory.DUPLICATE_USER_RECORDS.value == "Duplicate/Wrong User Records"
        )

    def test_error_category_is_enum(self):
        """Test that ErrorCategory is a proper enum."""
        from users.error_models import ErrorCategory

        assert issubclass(ErrorCategory, Enum)

        # Test that we can iterate over all values
        categories = list(ErrorCategory)
        assert len(categories) == 7

        # Test that each category has a string value
        for category in categories:
            assert isinstance(category.value, str)
            assert len(category.value) > 0


class TestUserContext:
    """Tests for UserContext creation and serialization."""

    def test_user_context_creation_from_user_entry(self):
        """Test UserContext creation from UserEntry."""
        from users.error_models import UserContext

        # Create a basic user entry
        user_entry = ActiveUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=[],
        )

        # Create UserContext from user entry
        user_context = UserContext.from_user_entry(user_entry)

        # Verify the context contains expected data
        assert user_context.email == "john.doe@example.com"
        assert user_context.name is not None
        assert user_context.name.first_name == "John"
        assert user_context.name.last_name == "Doe"
        assert user_context.auth_email == "john.auth@example.com"

    def test_user_context_creation_with_optional_fields(self):
        """Test UserContext creation with optional fields."""
        from users.error_models import UserContext

        # Create UserContext with minimal data
        user_context = UserContext(email="test@example.com")

        assert user_context.email == "test@example.com"
        assert user_context.name is None
        assert user_context.center_id is None
        assert user_context.registry_id is None
        assert user_context.auth_email is None

    def test_user_context_creation_with_all_fields(self):
        """Test UserContext creation with all fields populated."""
        from users.error_models import UserContext

        user_context = UserContext(
            email="test@example.com",
            name=PersonName(first_name="Jane", last_name="Smith"),
            center_id=456,
            registry_id="reg123",
            auth_email="jane.auth@example.com",
        )

        assert user_context.email == "test@example.com"
        assert user_context.name is not None
        assert user_context.name.first_name == "Jane"
        assert user_context.name.last_name == "Smith"
        assert user_context.center_id == 456
        assert user_context.registry_id == "reg123"
        assert user_context.auth_email == "jane.auth@example.com"

    def test_user_context_serialization(self):
        """Test UserContext serialization to dict and JSON."""
        from users.error_models import UserContext

        user_context = UserContext(
            email="test@example.com",
            name=PersonName(first_name="Alice", last_name="Johnson"),
            center_id=789,
            registry_id="reg456",
            auth_email="alice.auth@example.com",
        )

        # Test serialization to dict
        context_dict = user_context.model_dump()
        assert context_dict["email"] == "test@example.com"
        assert context_dict["name"]["first_name"] == "Alice"
        assert context_dict["name"]["last_name"] == "Johnson"
        assert context_dict["center_id"] == 789
        assert context_dict["registry_id"] == "reg456"
        assert context_dict["auth_email"] == "alice.auth@example.com"

        # Test JSON serialization
        context_json = user_context.model_dump_json()
        parsed_json = json.loads(context_json)
        assert parsed_json["email"] == "test@example.com"
        assert parsed_json["name"]["first_name"] == "Alice"

    def test_user_context_from_registered_user_entry(self):
        """Test UserContext creation from RegisteredUserEntry."""
        from users.error_models import UserContext

        # Create a registered user entry
        registered_entry = RegisteredUserEntry(
            name=PersonName(first_name="Bob", last_name="Wilson"),
            email="bob.wilson@example.com",
            auth_email="bob.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=999,
            authorizations=[],
            registry_id="reg789",
        )

        # Create UserContext from registered user entry
        user_context = UserContext.from_user_entry(registered_entry)

        # Verify the context contains expected data
        assert user_context.email == "bob.wilson@example.com"
        assert user_context.name is not None
        assert user_context.name.first_name == "Bob"
        assert user_context.name.last_name == "Wilson"
        assert user_context.auth_email == "bob.auth@example.com"


class TestErrorEvent:
    """Tests for ErrorEvent creation and serialization."""

    def test_error_event_creation(self):
        """Test ErrorEvent creation with required fields."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(
            email="test@example.com",
            name=PersonName(first_name="Test", last_name="User"),
        )

        error_details = {
            "message": "Test error message",
            "action_needed": "test_action",
        }

        error_event = ErrorEvent(
            category=ErrorCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            error_details=error_details,
        )

        # Verify the error event was created correctly
        assert error_event.category == "Unclaimed Records"
        assert error_event.user_context.email == "test@example.com"
        assert error_event.error_details["message"] == "Test error message"

        # Verify auto-generated fields
        assert isinstance(error_event.event_id, str)
        assert len(error_event.event_id) > 0
        assert isinstance(error_event.timestamp, datetime)

    def test_error_event_with_different_categories(self):
        """Test ErrorEvent creation with different categories."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(email="category@example.com")
        error_details = {"message": "Category test"}

        error_event = ErrorEvent(
            category=ErrorCategory.EMAIL_MISMATCH,
            user_context=user_context,
            error_details=error_details,
        )

        assert error_event.category == "Authentication Email Mismatch"

    def test_error_event_serialization(self):
        """Test ErrorEvent serialization to dict and JSON."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(
            email="serialize@example.com",
            name=PersonName(first_name="Serialize", last_name="Test"),
        )

        error_event = ErrorEvent(
            category=ErrorCategory.BAD_ORCID_CLAIMS,
            user_context=user_context,
            error_details={"message": "Serialization test"},
        )

        # Test serialization to dict
        event_dict = error_event.model_dump()
        assert event_dict["category"] == "Bad ORCID Claims"
        assert event_dict["user_context"]["email"] == "serialize@example.com"
        assert event_dict["error_details"]["message"] == "Serialization test"
        assert "event_id" in event_dict
        assert "timestamp" in event_dict

        # Test JSON serialization
        event_json = error_event.model_dump_json()
        parsed_json = json.loads(event_json)
        assert parsed_json["category"] == "Bad ORCID Claims"
        assert parsed_json["user_context"]["email"] == "serialize@example.com"

    def test_error_event_to_summary(self):
        """Test ErrorEvent to_summary method."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(email="summary@example.com")
        error_details = {"message": "Summary test message"}

        error_event = ErrorEvent(
            category=ErrorCategory.INSUFFICIENT_PERMISSIONS,
            user_context=user_context,
            error_details=error_details,
        )

        summary = error_event.to_summary()
        expected = (
            "Insufficient Permissions: summary@example.com - Summary test message"
        )
        assert summary == expected

    def test_error_event_to_summary_no_message(self):
        """Test ErrorEvent to_summary method when no message in details."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(email="nomessage@example.com")
        error_details = {"action_needed": "some_action"}

        error_event = ErrorEvent(
            category=ErrorCategory.DUPLICATE_USER_RECORDS,
            user_context=user_context,
            error_details=error_details,
        )

        summary = error_event.to_summary()
        expected = "Duplicate/Wrong User Records: nomessage@example.com - No details"
        assert summary == expected

    def test_error_event_default_values(self):
        """Test ErrorEvent creation with default values."""
        from users.error_models import ErrorCategory, ErrorEvent, UserContext

        user_context = UserContext(email="defaults@example.com")

        # Create without specifying event_id and timestamp
        error_event = ErrorEvent(
            category=ErrorCategory.UNVERIFIED_EMAIL,
            user_context=user_context,
            error_details={"message": "Default test"},
        )

        # Verify defaults were applied
        assert error_event.event_id is not None
        assert len(error_event.event_id) > 0
        assert error_event.timestamp is not None
        assert isinstance(error_event.timestamp, datetime)

        # Verify event_id is a valid UUID format
        try:
            uuid.UUID(error_event.event_id)
        except ValueError:
            pytest.fail("event_id should be a valid UUID string")
