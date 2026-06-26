"""Tests for user error models (TDD)."""

import json
import uuid
from datetime import datetime

import pytest
from users.authorizations import Authorizations
from users.event_models import EventCategory, EventType, UserContext, UserProcessEvent
from users.user_entry import CenterUserEntry, PersonName


class TestUserContext:
    """Tests for UserContext creation and serialization."""

    def test_user_context_creation_from_user_entry(self):
        """Test UserContext creation from UserEntry."""

        # Create a basic user entry
        user_entry = CenterUserEntry(
            name=PersonName(first_name="John", last_name="Doe"),
            email="john.doe@example.com",
            auth_email="john.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

        # Create UserContext from user entry
        user_context = UserContext.from_user_entry(user_entry)

        # Verify the context contains expected data
        assert user_context.email == "john.doe@example.com"
        assert user_context.name is not None
        assert user_context.name == "John Doe"
        assert user_context.auth_email == "john.auth@example.com"
        assert user_context.center_id == 123
        # registry_id should be None for unregistered entry
        assert user_context.registry_id is None

    def test_user_context_creation_with_optional_fields(self):
        """Test UserContext creation with optional fields."""

        # Create UserContext with minimal data
        user_context = UserContext(email="test@example.com")

        assert user_context.email == "test@example.com"
        assert user_context.name == "Unknown"
        assert user_context.center_id is None
        assert user_context.registry_id is None
        assert user_context.auth_email is None

    def test_user_context_creation_with_all_fields(self):
        """Test UserContext creation with all fields populated."""

        user_context = UserContext(
            email="test@example.com",
            name=PersonName(first_name="Jane", last_name="Smith"),
            center_id=456,
            registry_id="reg123",
            auth_email="jane.auth@example.com",
        )

        assert user_context.email == "test@example.com"
        assert user_context.name is not None
        assert user_context.name == "Jane Smith"
        assert user_context.center_id == 456
        assert user_context.registry_id == "reg123"
        assert user_context.auth_email == "jane.auth@example.com"

    def test_user_context_serialization(self):
        """Test UserContext serialization to dict and JSON."""

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
        assert context_dict["name"] == "Alice Johnson"
        assert context_dict["center_id"] == str(789)
        assert context_dict["registry_id"] == "reg456"
        assert context_dict["auth_email"] == "alice.auth@example.com"

        # Test JSON serialization
        context_json = user_context.model_dump_json()
        parsed_json = json.loads(context_json)
        assert parsed_json["email"] == "test@example.com"
        assert parsed_json["name"] == "Alice Johnson"

    def test_user_context_from_registered_user_entry(self):
        """Test UserContext creation from CenterUserEntry with
        registry_person."""
        from unittest.mock import Mock

        from users.user_registry import RegistryPerson

        # Create a mock RegistryPerson
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "reg789"

        # Create a registered user entry
        registered_entry = CenterUserEntry(
            name=PersonName(first_name="Bob", last_name="Wilson"),
            email="bob.wilson@example.com",
            auth_email="bob.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=999,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        registered_entry.register(mock_registry_person)

        # Create UserContext from registered user entry
        user_context = UserContext.from_user_entry(registered_entry)

        # Verify the context contains expected data
        assert user_context.email == "bob.wilson@example.com"
        assert user_context.name is not None
        assert user_context.name == "Bob Wilson"
        assert user_context.auth_email == "bob.auth@example.com"
        assert user_context.center_id == 999
        assert user_context.registry_id == "reg789"

    def test_user_context_from_unregistered_center_entry(self):
        """Test UserContext creation from unregistered CenterUserEntry."""

        # Create an unregistered center user entry
        unregistered_entry = CenterUserEntry(
            name=PersonName(first_name="Alice", last_name="Brown"),
            email="alice.brown@example.com",
            auth_email="alice.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=888,
            authorizations=Authorizations(),
            study_authorizations=[],
        )
        # Don't call register() - leave it unregistered

        # Create UserContext from unregistered user entry
        user_context = UserContext.from_user_entry(unregistered_entry)

        # Verify the context contains expected data
        assert user_context.email == "alice.brown@example.com"
        assert user_context.name == "Alice Brown"
        assert user_context.auth_email == "alice.auth@example.com"
        assert user_context.center_id == 888
        # registry_id should be None for unregistered entry
        assert user_context.registry_id is None


class TestUserProcessEvent:
    """Tests for UserProcessEvent creation and serialization."""

    def test_error_event_creation(self):
        """Test UserProcessEvent creation with required fields."""

        user_context = UserContext(
            email="test@example.com",
            name=PersonName(first_name="Test", last_name="User"),
        )

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            message="Test error message",
            action_needed="test_action",
        )

        # Verify the error event was created correctly
        assert error_event.category == "Unclaimed Records"
        assert error_event.user_context.email == "test@example.com"
        assert error_event.message == "Test error message"

        # Verify auto-generated fields
        assert isinstance(error_event.event_id, str)
        assert len(error_event.event_id) > 0
        assert isinstance(error_event.timestamp, datetime)

    def test_error_event_with_different_categories(self):
        """Test UserProcessEvent creation with different categories."""

        user_context = UserContext(email="category@example.com")

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=user_context,
            message="Category test",
        )

        assert error_event.category == "Incomplete Claims"

    def test_error_event_serialization(self):
        """Test UserProcessEvent serialization to dict and JSON."""

        user_context = UserContext(
            email="serialize@example.com",
            name=PersonName(first_name="Serialize", last_name="Test"),
        )

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.BAD_ORCID_CLAIMS,
            user_context=user_context,
            message="Serialization test",
        )

        # Test serialization to dict
        event_dict = error_event.model_dump()
        assert event_dict["category"] == "Bad ORCID Claims"
        assert event_dict["email"] == "serialize@example.com"
        assert event_dict["message"] == "Serialization test"
        assert "event_id" in event_dict
        assert "timestamp" in event_dict

        # Test JSON serialization
        event_json = error_event.model_dump_json()
        parsed_json = json.loads(event_json)
        assert parsed_json["category"] == "Bad ORCID Claims"
        assert parsed_json["email"] == "serialize@example.com"

    def test_error_event_to_summary(self):
        """Test UserProcessEvent to_summary method."""

        user_context = UserContext(email="summary@example.com")

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INSUFFICIENT_PERMISSIONS,
            user_context=user_context,
            message="Summary test message",
        )

        summary = error_event.to_summary()
        expected = (
            "Insufficient Permissions: summary@example.com - Summary test message"
        )
        assert summary == expected

    def test_error_event_to_summary_no_message(self):
        """Test UserProcessEvent to_summary method when no message provided."""

        user_context = UserContext(email="nomessage@example.com")

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.DUPLICATE_USER_RECORDS,
            user_context=user_context,
            message="",
        )

        summary = error_event.to_summary()
        expected = "Duplicate/Wrong User Records: nomessage@example.com - "
        assert summary == expected

    def test_error_event_default_values(self):
        """Test UserProcessEvent creation with default values."""

        user_context = UserContext(email="defaults@example.com")

        # Create without specifying event_id and timestamp
        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.MISSING_DIRECTORY_DATA,
            user_context=user_context,
            message="Default test",
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


class TestUserEventCollector:
    """Tests for UserEventCollector class."""

    def test_collector_initialization(self):
        """Test UserEventCollector initialization."""
        from users.event_models import UserEventCollector

        collector = UserEventCollector()

        assert collector.error_count() == 0
        assert not collector.has_errors()
        assert collector.get_errors() == []

    def test_collector_collect_single_error(self):
        """Test collecting a single error event."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()
        user_context = UserContext(email="test@example.com")
        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            message="Test error",
        )

        collector.collect(error_event)

        assert collector.error_count() == 1
        assert collector.has_errors()
        errors = collector.get_errors()
        assert len(errors) == 1
        assert errors[0] == error_event

    def test_collector_collect_multiple_errors(self):
        """Test collecting multiple error events."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()
        user_context1 = UserContext(email="user1@example.com")
        user_context2 = UserContext(email="user2@example.com")

        error_event1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context1,
            message="First error",
        )
        error_event2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=user_context2,
            message="Second error",
        )

        collector.collect(error_event1)
        collector.collect(error_event2)

        assert collector.error_count() == 2
        assert collector.has_errors()
        errors = collector.get_errors()
        assert len(errors) == 2
        assert error_event1 in errors
        assert error_event2 in errors

    def test_collector_get_errors_by_category(self):
        """Test getting errors grouped by category."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()

        error1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user1@example.com"),
            message="First unclaimed",
        )
        error2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user2@example.com"),
            message="Second unclaimed",
        )
        error3 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext(email="user3@example.com"),
            message="Incomplete claim",
        )

        collector.collect(error1)
        collector.collect(error2)
        collector.collect(error3)

        errors_by_category = collector.get_errors_by_category()

        assert len(errors_by_category) == 2
        assert len(errors_by_category[EventCategory.UNCLAIMED_RECORDS]) == 2
        assert len(errors_by_category[EventCategory.INCOMPLETE_CLAIM]) == 1

    def test_collector_get_errors_for_category(self):
        """Test getting errors for a specific category."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()

        error1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user1@example.com"),
            message="Unclaimed",
        )
        error2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext(email="user2@example.com"),
            message="Incomplete claim",
        )

        collector.collect(error1)
        collector.collect(error2)

        unclaimed_errors = collector.get_events_for_category(
            EventCategory.UNCLAIMED_RECORDS
        )
        assert len(unclaimed_errors) == 1
        assert unclaimed_errors[0] == error1

        incomplete_errors = collector.get_events_for_category(
            EventCategory.INCOMPLETE_CLAIM
        )
        assert len(incomplete_errors) == 1
        assert incomplete_errors[0] == error2

        # Test non-existent category - use a category that exists but has no events
        missing_data_errors = collector.get_events_for_category(
            EventCategory.MISSING_DIRECTORY_DATA
        )
        assert len(missing_data_errors) == 0

    def test_collector_count_by_category(self):
        """Test counting errors by category."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()

        error1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user1@example.com"),
            message="First",
        )
        error2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user2@example.com"),
            message="Second",
        )
        error3 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext(email="user3@example.com"),
            message="Incomplete claim",
        )

        collector.collect(error1)
        collector.collect(error2)
        collector.collect(error3)

        counts = collector.count_by_category()

        assert counts["Unclaimed Records"] == 2
        assert counts["Incomplete Claims"] == 1
        assert len(counts) == 2

    def test_collector_get_affected_users(self):
        """Test getting list of affected users."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()

        error1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user1@example.com"),
            message="Error 1",
        )
        error2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext(email="user2@example.com"),
            message="Error 2",
        )
        error3 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="user1@example.com"),
            message="Error 3",
        )

        collector.collect(error1)
        collector.collect(error2)
        collector.collect(error3)

        affected_users = collector.get_affected_users()

        assert len(affected_users) == 2
        assert "user1@example.com" in affected_users
        assert "user2@example.com" in affected_users

    def test_collector_clear(self):
        """Test clearing all errors from the collector."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()
        user_context = UserContext(email="test@example.com")
        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            message="Test error",
        )

        collector.collect(error_event)
        assert collector.has_errors()
        assert collector.error_count() == 1

        collector.clear()
        assert not collector.has_errors()
        assert collector.error_count() == 0
        assert collector.get_errors() == []
        assert collector.get_errors_by_category() == {}
        assert collector.get_affected_users() == []

    def test_collector_has_errors_states(self):
        """Test has_errors method in different states."""
        from users.event_models import (
            UserEventCollector,
        )

        collector = UserEventCollector()

        # Initially no errors
        assert not collector.has_errors()

        # After adding an error
        user_context = UserContext(email="test@example.com")
        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            message="Test error",
        )
        collector.collect(error_event)
        assert collector.has_errors()

        # After clearing
        collector.clear()
        assert not collector.has_errors()


class TestCreateUserProcessEvent:
    """Tests for create_error_event utility function."""

    def test_create_error_event_basic(self):
        """Test basic error event creation."""

        user_context = UserContext(email="test@example.com")

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=user_context,
            message="Test error message",
        )

        assert error_event.category == "Unclaimed Records"
        assert error_event.user_context == user_context
        assert error_event.message == "Test error message"
        assert isinstance(error_event.event_id, str)
        assert len(error_event.event_id) > 0
        assert isinstance(error_event.timestamp, datetime)

    def test_create_error_event_different_categories(self):
        """Test creating error events with different categories."""

        user_context = UserContext(email="test@example.com")

        # Test each category
        categories_to_test = [
            (EventCategory.UNCLAIMED_RECORDS, "Unclaimed Records"),
            (EventCategory.INCOMPLETE_CLAIM, "Incomplete Claims"),
            (EventCategory.BAD_ORCID_CLAIMS, "Bad ORCID Claims"),
            (
                EventCategory.MISSING_DIRECTORY_PERMISSIONS,
                "Missing Directory Permissions",
            ),
            (EventCategory.MISSING_DIRECTORY_DATA, "Missing Directory Data"),
            (EventCategory.MISSING_REGISTRY_DATA, "Missing Registry Data"),
            (EventCategory.INSUFFICIENT_PERMISSIONS, "Insufficient Permissions"),
            (
                EventCategory.DUPLICATE_USER_RECORDS,
                "Duplicate/Wrong User Records",
            ),
            (EventCategory.FLYWHEEL_ERROR, "Flywheel Errors"),
            (EventCategory.DOMAIN_NEAR_MISS, "Domain Near-Miss"),
            (EventCategory.NAME_NEAR_MISS, "Name Near-Miss"),
            (EventCategory.COMBINED_NEAR_MISS, "Combined Signal Near-Miss"),
            (EventCategory.WRONG_IDP_SELECTION, "Wrong IdP Selection"),
        ]

        for category_enum, expected_value in categories_to_test:
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=category_enum,
                user_context=user_context,
                message="Test message",
            )
            assert error_event.category == expected_value

    def test_create_error_event_with_minimal_details(self):
        """Test creating error event with minimal details."""

        user_context = UserContext(email="minimal@example.com")

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.FLYWHEEL_ERROR,
            user_context=user_context,
            message="",
        )

        assert error_event.category == "Flywheel Errors"
        assert error_event.user_context.email == "minimal@example.com"
        assert error_event.message == ""

        # Test to_summary with empty message
        summary = error_event.to_summary()
        assert "Flywheel Errors" in summary


class TestNearMissEventCategories:
    """Tests for new near-miss and wrong-IdP event categories."""

    def test_domain_near_miss_category_value(self):
        """Test DOMAIN_NEAR_MISS category has correct string value."""
        assert EventCategory.DOMAIN_NEAR_MISS.value == "Domain Near-Miss"

    def test_name_near_miss_category_value(self):
        """Test NAME_NEAR_MISS category has correct string value."""
        assert EventCategory.NAME_NEAR_MISS.value == "Name Near-Miss"

    def test_combined_near_miss_category_value(self):
        """Test COMBINED_NEAR_MISS category has correct string value."""
        assert EventCategory.COMBINED_NEAR_MISS.value == "Combined Signal Near-Miss"

    def test_wrong_idp_selection_category_value(self):
        """Test WRONG_IDP_SELECTION category has correct string value."""
        assert EventCategory.WRONG_IDP_SELECTION.value == "Wrong IdP Selection"

    def test_domain_near_miss_serializes_in_event(self):
        """Test DOMAIN_NEAR_MISS serializes correctly in UserProcessEvent."""
        user_context = UserContext(
            email="user@med.umich.edu",
            name="Test User",
            center_id=123,
        )
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.DOMAIN_NEAR_MISS,
            user_context=user_context,
            message="Domain near-miss: candidate found",
            action_needed="review_potential_duplicate",
        )

        assert event.category == "Domain Near-Miss"
        event_dict = event.model_dump()
        assert event_dict["category"] == "Domain Near-Miss"
        assert event_dict["email"] == "user@med.umich.edu"
        assert event_dict["message"] == "Domain near-miss: candidate found"

    def test_name_near_miss_serializes_in_event(self):
        """Test NAME_NEAR_MISS serializes correctly in UserProcessEvent."""
        user_context = UserContext(email="user@example.com", name="John Doe")
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.NAME_NEAR_MISS,
            user_context=user_context,
            message="Name near-miss: candidate found",
            action_needed="review_potential_duplicate",
        )

        assert event.category == "Name Near-Miss"
        event_dict = event.model_dump()
        assert event_dict["category"] == "Name Near-Miss"

    def test_combined_near_miss_serializes_in_event(self):
        """Test COMBINED_NEAR_MISS serializes correctly in UserProcessEvent."""
        user_context = UserContext(email="user@example.com", name="Jane Smith")
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.COMBINED_NEAR_MISS,
            user_context=user_context,
            message="Combined near-miss: domain and name match",
            action_needed="review_potential_duplicate",
        )

        assert event.category == "Combined Signal Near-Miss"
        event_dict = event.model_dump()
        assert event_dict["category"] == "Combined Signal Near-Miss"

    def test_wrong_idp_selection_serializes_in_event(self):
        """Test WRONG_IDP_SELECTION serializes correctly in
        UserProcessEvent."""
        user_context = UserContext(email="user@umich.edu", name="Test User")
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.WRONG_IDP_SELECTION,
            user_context=user_context,
            message="Wrong IdP: expected University of Michigan, got ORCID",
            action_needed="delete_bad_record_and_reclaim",
        )

        assert event.category == "Wrong IdP Selection"
        event_dict = event.model_dump()
        assert event_dict["category"] == "Wrong IdP Selection"

    def test_near_miss_categories_to_field_name(self):
        """Test to_field_name() for new categories."""
        assert EventCategory.DOMAIN_NEAR_MISS.to_field_name() == "domain_near-miss"
        assert EventCategory.NAME_NEAR_MISS.to_field_name() == "name_near-miss"
        assert (
            EventCategory.COMBINED_NEAR_MISS.to_field_name()
            == "combined_signal_near-miss"
        )
        assert (
            EventCategory.WRONG_IDP_SELECTION.to_field_name() == "wrong_idp_selection"
        )

    def test_near_miss_event_to_summary(self):
        """Test to_summary() for near-miss events."""
        user_context = UserContext(email="user@example.com")
        event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.DOMAIN_NEAR_MISS,
            user_context=user_context,
            message="Domain near-miss found",
        )
        summary = event.to_summary()
        assert "Domain Near-Miss" in summary
        assert "user@example.com" in summary
        assert "Domain near-miss found" in summary

    def test_collector_categorizes_near_miss_events(self):
        """Test UserEventCollector correctly categorizes near-miss events."""
        from users.event_models import UserEventCollector

        collector = UserEventCollector()

        domain_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.DOMAIN_NEAR_MISS,
            user_context=UserContext(email="user1@example.com"),
            message="Domain near-miss",
        )
        name_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.NAME_NEAR_MISS,
            user_context=UserContext(email="user2@example.com"),
            message="Name near-miss",
        )
        combined_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.COMBINED_NEAR_MISS,
            user_context=UserContext(email="user3@example.com"),
            message="Combined near-miss",
        )
        wrong_idp_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.WRONG_IDP_SELECTION,
            user_context=UserContext(email="user4@example.com"),
            message="Wrong IdP",
        )

        collector.collect(domain_event)
        collector.collect(name_event)
        collector.collect(combined_event)
        collector.collect(wrong_idp_event)

        assert collector.error_count() == 4

        domain_events = collector.get_events_for_category(
            EventCategory.DOMAIN_NEAR_MISS
        )
        assert len(domain_events) == 1
        assert domain_events[0].user_context.email == "user1@example.com"

        name_events = collector.get_events_for_category(EventCategory.NAME_NEAR_MISS)
        assert len(name_events) == 1

        combined_events = collector.get_events_for_category(
            EventCategory.COMBINED_NEAR_MISS
        )
        assert len(combined_events) == 1

        wrong_idp_events = collector.get_events_for_category(
            EventCategory.WRONG_IDP_SELECTION
        )
        assert len(wrong_idp_events) == 1

        counts = collector.count_by_category()
        assert counts["Domain Near-Miss"] == 1
        assert counts["Name Near-Miss"] == 1
        assert counts["Combined Signal Near-Miss"] == 1
        assert counts["Wrong IdP Selection"] == 1
