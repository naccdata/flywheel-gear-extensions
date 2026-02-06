"""Tests for error notification generation and template system."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from notifications.email import EmailClient
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)
from users.event_notifications import (
    ConsolidatedNotificationData,
    UserEventNotificationGenerator,
)
from users.user_entry import PersonName


@pytest.fixture
def mock_email_client():
    """Create a mock email client."""
    return Mock(spec=EmailClient)


@pytest.fixture
def notification_generator(mock_email_client):
    """Create an error notification generator with mock client."""
    return UserEventNotificationGenerator(
        email_client=mock_email_client, configuration_set_name="test-config"
    )


@pytest.fixture
def sample_error_event():
    """Create a sample error event for testing."""
    return UserProcessEvent(
        event_type=EventType.ERROR,
        category=EventCategory.UNCLAIMED_RECORDS,
        user_context=UserContext(
            email="test@example.com",
            name=PersonName(first_name="Test", last_name="User"),
            auth_email="auth@example.com",
        ),
        message="User not found in registry",
        action_needed="check_registry_status",
    )


@pytest.fixture
def collector():
    """Create an error collector for testing."""
    return UserEventCollector()


class TestConsolidatedNotificationData:
    """Tests for ConsolidatedNotificationData model."""

    def test_create_notification_data(self):
        """Test creating notification data model."""
        data = ConsolidatedNotificationData(
            gear_name="user_management",
            execution_timestamp=datetime.now().isoformat(),
            total_events=1,
            events_by_category={"Unclaimed Records": 1},
            event_summaries=["Test summary"],
            affected_users=["test@example.com"],
            affected_users_count=1,
            category_details={},
        )

        assert data.gear_name == "user_management"
        assert data.total_events == 1
        assert len(data.affected_users) == 1


class TestErrorNotificationGenerator:
    """Tests for ErrorNotificationGenerator."""

    def test_create_notification_data(
        self, notification_generator, collector, sample_error_event
    ):
        """Test creating notification data from error collector."""
        collector.collect(sample_error_event)

        notification_data = notification_generator.create_notification_data(
            collector, "user_management"
        )

        assert notification_data.gear_name == "user_management"
        assert notification_data.total_events == 1
        assert len(notification_data.affected_users) == 1
        assert notification_data.affected_users[0] == "test@example.com"
        assert "Unclaimed Records" in notification_data.events_by_category
        assert "Unclaimed Records" in notification_data.category_details
        assert len(notification_data.category_details["Unclaimed Records"]) == 1

    def test_create_notification_data_multiple_categories(
        self, notification_generator, collector
    ):
        """Test creating notification data with multiple error categories."""
        error1 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="test1@example.com"),
            message="Unclaimed record",
        )
        error2 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext(email="test2@example.com"),
            message="Another unclaimed record",
        )
        error3 = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext(email="test3@example.com"),
            message="Incomplete claim",
        )

        collector.collect(error1)
        collector.collect(error2)
        collector.collect(error3)

        notification_data = notification_generator.create_notification_data(
            collector, "user_management"
        )

        assert notification_data.total_events == 3
        assert len(notification_data.affected_users) == 3
        assert notification_data.events_by_category["Unclaimed Records"] == 2
        assert notification_data.events_by_category["Incomplete Claims"] == 1
        assert len(notification_data.category_details["Unclaimed Records"]) == 2
        assert len(notification_data.category_details["Incomplete Claims"]) == 1

    def test_send_consolidated_notification(
        self, notification_generator, mock_email_client
    ):
        """Test sending consolidated notification."""
        notification_data = ConsolidatedNotificationData(
            gear_name="user_management",
            execution_timestamp=datetime.now().isoformat(),
            total_events=1,
            events_by_category={"Unclaimed Records": 1},
            event_summaries=["Test summary"],
            affected_users=["test@example.com"],
            affected_users_count=1,
            category_details={},
        )

        mock_email_client.send.return_value = "message-id-123"

        message_id = notification_generator.send_consolidated_notification(
            ["support@example.com"], notification_data
        )

        assert message_id == "message-id-123"
        mock_email_client.send.assert_called_once()

    def test_send_consolidated_notification_no_emails(
        self, notification_generator, mock_email_client
    ):
        """Test sending notification with no support emails."""
        notification_data = ConsolidatedNotificationData(
            gear_name="user_management",
            execution_timestamp=datetime.now().isoformat(),
            total_events=1,
            events_by_category={"Unclaimed Records": 1},
            event_summaries=["Test summary"],
            affected_users=["test@example.com"],
            affected_users_count=1,
            category_details={},
        )

        message_id = notification_generator.send_consolidated_notification(
            [], notification_data
        )

        assert message_id is None
        mock_email_client.send.assert_not_called()

    def test_send_error_notification(
        self,
        notification_generator,
        mock_email_client,
        collector,
        sample_error_event,
    ):
        """Test sending error notification (main entry point)."""
        collector.collect(sample_error_event)
        mock_email_client.send.return_value = "message-id-456"

        message_id = notification_generator.send_event_notification(
            collector, "user_management", ["support@example.com"]
        )

        assert message_id == "message-id-456"
        mock_email_client.send.assert_called_once()

    def test_send_error_notification_no_errors(
        self, notification_generator, mock_email_client, collector
    ):
        """Test sending notification with no errors."""
        message_id = notification_generator.send_event_notification(
            collector, "user_management", ["support@example.com"]
        )

        assert message_id is None
        mock_email_client.send.assert_not_called()
