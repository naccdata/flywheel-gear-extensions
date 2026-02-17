"""Tests for notification batching functionality."""

from unittest.mock import MagicMock

import pytest
from notifications.email import EmailClient
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)
from users.event_notifications import UserEventNotificationGenerator


@pytest.fixture
def mock_email_client():
    """Create a mock email client."""
    client = MagicMock(spec=EmailClient)
    client.send.return_value = "test-message-id"
    return client


@pytest.fixture
def notification_generator(mock_email_client):
    """Create a notification generator with default settings."""
    return UserEventNotificationGenerator(
        email_client=mock_email_client,
        configuration_set_name="test-config",
    )


@pytest.fixture
def small_batch_generator(mock_email_client):
    """Create a notification generator with small batch size for testing."""
    # Use 2KB limit to force batching with small datasets
    return UserEventNotificationGenerator(
        email_client=mock_email_client,
        configuration_set_name="test-config",
        max_template_data_bytes=2000,
    )


def create_test_event(
    email: str,
    category: EventCategory = EventCategory.FLYWHEEL_ERROR,
    message: str = "Test error",
) -> UserProcessEvent:
    """Helper to create a test error event."""
    return UserProcessEvent(
        event_type=EventType.ERROR,
        category=category,
        user_context=UserContext(
            email=email,
            name=f"User {email}",
            center_id=1,
        ),
        message=message,
        action_needed="Test action",
    )


class TestNotificationSizeEstimation:
    """Tests for notification size estimation."""

    def test_estimate_size_returns_bytes(self, notification_generator):
        """Test that estimate_size returns a positive byte count."""
        collector = UserEventCollector()
        collector.collect(create_test_event("user1@example.com"))

        notification = notification_generator.create_notification_data(
            collector, "test-gear"
        )

        size = notification.estimate_size()
        assert size > 0
        assert isinstance(size, int)

    def test_estimate_size_increases_with_events(self, notification_generator):
        """Test that size increases as more events are added."""
        collector1 = UserEventCollector()
        collector1.collect(create_test_event("user1@example.com"))

        collector2 = UserEventCollector()
        collector2.collect(create_test_event("user1@example.com"))
        collector2.collect(create_test_event("user2@example.com"))
        collector2.collect(create_test_event("user3@example.com"))

        notification1 = notification_generator.create_notification_data(
            collector1, "test-gear"
        )
        notification2 = notification_generator.create_notification_data(
            collector2, "test-gear"
        )

        assert notification2.estimate_size() > notification1.estimate_size()


class TestSingleNotification:
    """Tests for notifications that fit in a single email."""

    def test_small_notification_not_batched(
        self, notification_generator, mock_email_client
    ):
        """Test that small notifications are sent as single email."""
        collector = UserEventCollector()
        collector.collect(create_test_event("user1@example.com"))
        collector.collect(create_test_event("user2@example.com"))

        notifications = notification_generator.create_batched_notifications(
            collector, "test-gear"
        )

        assert len(notifications) == 1
        assert notifications[0].batch_number is None
        assert notifications[0].total_batches is None
        assert notifications[0].total_events == 2

    def test_send_single_notification(self, notification_generator, mock_email_client):
        """Test sending a single notification."""
        collector = UserEventCollector()
        collector.collect(create_test_event("user1@example.com"))

        message_id = notification_generator.send_event_notification(
            collector, "test-gear", ["support@example.com"]
        )

        assert message_id == "test-message-id"
        assert mock_email_client.send.call_count == 1


class TestBatchedNotifications:
    """Tests for notifications that require batching."""

    def test_large_notification_is_batched(self, small_batch_generator):
        """Test that large notifications are split into batches."""
        collector = UserEventCollector()

        # Add many events to exceed the 2KB limit
        for i in range(50):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    message=f"This is a detailed error message for user {i} "
                    "with lots of text to increase the size",
                )
            )

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Should be split into multiple batches
        assert len(notifications) > 1

        # Check batch metadata
        for i, notification in enumerate(notifications, 1):
            assert notification.batch_number == i
            assert notification.total_batches == len(notifications)

    def test_batches_contain_all_events(self, small_batch_generator):
        """Test that all events are included across batches."""
        collector = UserEventCollector()

        # Add many events
        num_events = 50
        for i in range(num_events):
            collector.collect(create_test_event(f"user{i}@example.com"))

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Count total events across all batches
        total_events = sum(n.total_events for n in notifications)
        assert total_events == num_events

    def test_batch_sizes_within_limit(self, small_batch_generator):
        """Test that each batch is within the size limit."""
        collector = UserEventCollector()

        # Add many events
        for i in range(50):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    message="Long error message " * 10,
                )
            )

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Each batch should be within limit
        for notification in notifications:
            size = notification.estimate_size()
            assert size <= 2000, f"Batch size {size} exceeds limit"

    def test_send_multiple_batches(self, small_batch_generator, mock_email_client):
        """Test that multiple batches are all sent."""
        collector = UserEventCollector()

        # Add many events to force batching
        for i in range(50):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    message="Error message " * 10,
                )
            )

        message_id = small_batch_generator.send_event_notification(
            collector, "test-gear", ["support@example.com"]
        )

        # Should return first message ID
        assert message_id == "test-message-id"

        # Should have sent multiple emails
        assert mock_email_client.send.call_count > 1


class TestCategoryBatching:
    """Tests for batching across different error categories."""

    def test_multiple_categories_batched(self, small_batch_generator):
        """Test batching with multiple error categories."""
        collector = UserEventCollector()

        # Add events from different categories
        for i in range(20):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    category=EventCategory.FLYWHEEL_ERROR,
                    message="Flywheel error " * 10,
                )
            )

        for i in range(20, 40):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    category=EventCategory.MISSING_DIRECTORY_DATA,
                    message="Directory error " * 10,
                )
            )

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Should be batched
        assert len(notifications) > 1

        # Verify all categories are represented
        all_categories = set()
        for notification in notifications:
            all_categories.update(notification.events_by_category.keys())

        assert "Flywheel Errors" in all_categories
        assert "Missing Directory Data" in all_categories

    def test_batch_affected_users_accurate(self, small_batch_generator):
        """Test that affected_users list is accurate for each batch."""
        collector = UserEventCollector()

        # Add events
        for i in range(30):
            collector.collect(create_test_event(f"user{i}@example.com"))

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Collect all unique users across batches
        all_users = set()
        for notification in notifications:
            # Each batch should have users
            assert len(notification.affected_users) > 0
            assert notification.affected_users_count == len(notification.affected_users)
            all_users.update(notification.affected_users)

        # All users should be represented
        assert len(all_users) == 30


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_no_errors_no_notification(self, notification_generator, mock_email_client):
        """Test that no notification is sent when there are no errors."""
        collector = UserEventCollector()

        message_id = notification_generator.send_event_notification(
            collector, "test-gear", ["support@example.com"]
        )

        assert message_id is None
        assert mock_email_client.send.call_count == 0

    def test_no_support_emails(self, notification_generator, mock_email_client):
        """Test handling when no support emails are configured."""
        collector = UserEventCollector()
        collector.collect(create_test_event("user1@example.com"))

        message_id = notification_generator.send_event_notification(
            collector, "test-gear", []
        )

        assert message_id is None
        assert mock_email_client.send.call_count == 0

    def test_single_large_event(self, small_batch_generator):
        """Test handling of a single event that's very large."""
        collector = UserEventCollector()

        # Create one event with a very long message
        collector.collect(
            create_test_event(
                "user@example.com",
                message="Very long error message " * 200,
            )
        )

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Should still create at least one notification
        assert len(notifications) >= 1
        assert notifications[0].total_events == 1

    def test_email_send_failure_handled(
        self, notification_generator, mock_email_client
    ):
        """Test that email send failures are handled gracefully."""
        mock_email_client.send.side_effect = Exception("Send failed")

        collector = UserEventCollector()
        collector.collect(create_test_event("user1@example.com"))

        # Should not raise exception
        message_id = notification_generator.send_event_notification(
            collector, "test-gear", ["support@example.com"]
        )

        assert message_id is None


class TestBatchMetadata:
    """Tests for batch metadata fields."""

    def test_batch_numbers_sequential(self, small_batch_generator):
        """Test that batch numbers are sequential starting from 1."""
        collector = UserEventCollector()

        for i in range(50):
            collector.collect(
                create_test_event(
                    f"user{i}@example.com",
                    message="Error " * 10,
                )
            )

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        # Check sequential numbering
        for i, notification in enumerate(notifications, 1):
            assert notification.batch_number == i

    def test_total_batches_consistent(self, small_batch_generator):
        """Test that total_batches is consistent across all batches."""
        collector = UserEventCollector()

        for i in range(50):
            collector.collect(create_test_event(f"user{i}@example.com"))

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        total = len(notifications)

        # All batches should have same total_batches value
        for notification in notifications:
            assert notification.total_batches == total

    def test_event_summaries_omitted_in_batches(self, small_batch_generator):
        """Test that event_summaries are omitted in batched notifications."""
        collector = UserEventCollector()

        for i in range(50):
            collector.collect(create_test_event(f"user{i}@example.com"))

        notifications = small_batch_generator.create_batched_notifications(
            collector, "test-gear"
        )

        if len(notifications) > 1:
            # Batched notifications should have empty summaries
            for notification in notifications:
                assert notification.event_summaries == []
