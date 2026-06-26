"""Notification generation and template system for error handling."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from notifications.email import BaseTemplateModel, DestinationModel, EmailClient
from pydantic import SerializationInfo, SerializerFunctionWrapHandler, model_serializer

from users.event_models import EventCategory, UserEventCollector, UserProcessEvent

log = logging.getLogger(__name__)

# AWS SES TemplateData limit is 262,144 bytes (256 KB)
# Use a conservative limit to account for JSON overhead
MAX_TEMPLATE_DATA_BYTES = 250_000  # 250 KB safety margin


class ConsolidatedNotificationData(BaseTemplateModel):
    """Template data model for consolidated error notifications.

    Extends BaseTemplateModel to work with existing AWS SES template
    infrastructure.
    """

    gear_name: str
    execution_timestamp: str
    total_events: int
    events_by_category: Dict[str, int]
    event_summaries: List[str]
    affected_users: List[str]
    affected_users_count: int
    category_details: Dict[str, List[Dict[str, str]]]
    batch_number: Optional[int] = None
    total_batches: Optional[int] = None

    @model_serializer(mode="wrap")
    def serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> Dict[str, Any]:
        """Serialize model, flattening category_details into top-level
        fields."""
        data = handler(self)

        # Flatten each category into a top-level snake_case field
        for k, v in self.category_details.items():
            data[k] = v

        return data

    def estimate_size(self) -> int:
        """Estimate the serialized JSON size in bytes.

        Returns:
            Estimated size in bytes
        """
        try:
            json_str = self.model_dump_json(exclude_none=True)
            return len(json_str.encode("utf-8"))
        except Exception as error:
            log.warning("Failed to estimate notification size: %s", str(error))
            return 0


class UserEventNotificationGenerator:
    """Generates notifications for error events using AWS SES templates.

    Uses a single consolidated template (error-consolidated) that
    includes all error categories in one email notification.

    Automatically splits large notifications into multiple batches
    to stay within AWS SES template data size limits.
    """

    def __init__(
        self,
        email_client: EmailClient,
        configuration_set_name: str,
        max_template_data_bytes: int = MAX_TEMPLATE_DATA_BYTES,
    ):
        """Initialize the error notification generator.

        Args:
            email_client: The EmailClient instance for sending notifications
            configuration_set_name: The AWS SES configuration set name
            max_template_data_bytes: Maximum size in bytes for template data
                (default: 250KB, can be overridden for testing)
        """
        self.__email_client = email_client
        self.__configuration_set_name = configuration_set_name
        self.__max_template_data_bytes = max_template_data_bytes

    def _split_category_details(
        self,
        category_details: Dict[str, List[Dict[str, str]]],
        max_size: int,
    ) -> List[Dict[str, List[Dict[str, str]]]]:
        """Split category details into batches that fit within size limit.

        Args:
            category_details: The full category details dictionary
            max_size: Maximum size in bytes for each batch

        Returns:
            List of category detail dictionaries, each within size limit
        """
        batches = []
        current_batch: Dict[str, List[Dict[str, str]]] = {}

        # Estimate base size (without category details)
        base_size = len(
            json.dumps(
                {
                    "gear_name": "test",
                    "execution_timestamp": datetime.now().isoformat(),
                    "total_events": 0,
                    "events_by_category": {},
                    "event_summaries": [],
                    "affected_users": [],
                    "affected_users_count": 0,
                }
            ).encode("utf-8")
        )

        current_size = base_size

        for category, events in category_details.items():
            # Initialize category in current batch if needed
            if category not in current_batch:
                current_batch[category] = []

            for event in events:
                event_size = len(json.dumps(event).encode("utf-8"))

                # Add category key overhead if this is first event in category
                category_overhead = 0
                if not current_batch[category]:
                    # Account for category key in JSON: "category_name": []
                    category_overhead = len(json.dumps(category).encode("utf-8")) + 4

                # If adding this event would exceed limit and current batch
                # has content, start new batch
                if current_size + event_size + category_overhead > max_size and any(
                    events for events in current_batch.values()
                ):
                    batches.append(current_batch)
                    current_batch = {category: []}
                    current_size = base_size
                    # Recalculate category overhead for new batch
                    category_overhead = len(json.dumps(category).encode("utf-8")) + 4

                current_batch[category].append(event)
                current_size += event_size + category_overhead

        # Add final batch if not empty
        if current_batch and any(events for events in current_batch.values()):
            batches.append(current_batch)

        return batches if batches else [{}]

    def create_notification_data(
        self, collector: UserEventCollector, gear_name: str
    ) -> ConsolidatedNotificationData:
        """Create template data for consolidated notification.

        Args:
            collector: The UserEventCollector with categorized errors
            gear_name: Name of the gear that generated the errors

        Returns:
            ConsolidatedNotificationData ready for template rendering
        """
        # Get errors grouped by category from the collector
        grouped = collector.get_errors_by_category()

        # Use event's to_template_dict() method for serialization
        category_details = {
            category.value: [
                error.model_dump(exclude_none=True) for error in category_events
            ]
            for category, category_events in grouped.items()
        }

        # Get all errors as flat list for summaries
        all_errors = collector.get_errors()
        affected_users = collector.get_affected_users()

        return ConsolidatedNotificationData(
            gear_name=gear_name,
            execution_timestamp=datetime.now().isoformat(),
            total_events=collector.error_count(),
            events_by_category=collector.count_by_category(),
            event_summaries=[error.to_summary() for error in all_errors],
            affected_users=affected_users,
            affected_users_count=len(affected_users),
            category_details=category_details,
        )

    def _build_category_details(
        self,
        batch_events: List[tuple[EventCategory, UserProcessEvent]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build category details dictionary from batch events.

        Args:
            batch_events: List of (category, event) tuples

        Returns:
            Dictionary mapping category names to lists of event dicts
        """
        category_details: Dict[str, List[Dict[str, Any]]] = {}
        for category, event in batch_events:
            cat_value = category.value
            if cat_value not in category_details:
                category_details[cat_value] = []
            category_details[cat_value].append(event.model_dump(exclude_none=True))
        return category_details

    def _get_affected_users(
        self,
        batch_events: List[tuple[EventCategory, UserProcessEvent]],
    ) -> List[str]:
        """Get list of affected users from batch events.

        Args:
            batch_events: List of (category, event) tuples

        Returns:
            List of unique user email addresses
        """
        users = set()
        for _, event in batch_events:
            users.add(event.user_context.email)
        return list(users)

    def _create_test_notification(
        self,
        gear_name: str,
        execution_timestamp: str,
        batch_events: List[tuple[EventCategory, UserProcessEvent]],
    ) -> ConsolidatedNotificationData:
        """Create a test notification to check size.

        Args:
            gear_name: Name of the gear
            execution_timestamp: Timestamp for the notification
            batch_events: List of (category, event) tuples

        Returns:
            Test notification object
        """
        category_details = self._build_category_details(batch_events)
        affected_users = self._get_affected_users(batch_events)

        events_by_category = {
            cat_value: len(events_list)
            for cat_value, events_list in category_details.items()
        }

        return ConsolidatedNotificationData(
            gear_name=gear_name,
            execution_timestamp=execution_timestamp,
            total_events=len(batch_events),
            events_by_category=events_by_category,
            event_summaries=[],  # Omit to save space
            affected_users=affected_users,
            affected_users_count=len(affected_users),
            category_details=category_details,
            batch_number=1,  # Placeholder
            total_batches=1,  # Placeholder
        )

    def _split_events_into_batches(
        self,
        all_events: List[tuple[EventCategory, UserProcessEvent]],
        gear_name: str,
        execution_timestamp: str,
    ) -> List[List[tuple[EventCategory, UserProcessEvent]]]:
        """Split events into batches that fit within size limit.

        Args:
            all_events: All events to split
            gear_name: Name of the gear
            execution_timestamp: Timestamp for notifications

        Returns:
            List of event batches
        """
        batches: List[List[tuple[EventCategory, UserProcessEvent]]] = []
        current_batch_events: List[tuple[EventCategory, UserProcessEvent]] = []

        for category, event in all_events:
            # Try adding this event to current batch
            test_batch_events = [*current_batch_events, (category, event)]

            # Create test notification to check size
            test_notification = self._create_test_notification(
                gear_name, execution_timestamp, test_batch_events
            )
            test_size = test_notification.estimate_size()

            # If adding this event would exceed limit, save current batch
            if test_size > self.__max_template_data_bytes and current_batch_events:
                batches.append(current_batch_events)
                current_batch_events = [(category, event)]
            else:
                current_batch_events = test_batch_events

        # Add final batch
        if current_batch_events:
            batches.append(current_batch_events)

        return batches

    def _create_batch_notification(
        self,
        gear_name: str,
        execution_timestamp: str,
        batch_events: List[tuple[EventCategory, UserProcessEvent]],
        batch_number: int,
        total_batches: int,
    ) -> ConsolidatedNotificationData:
        """Create a notification for a single batch.

        Args:
            gear_name: Name of the gear
            execution_timestamp: Timestamp for the notification
            batch_events: Events in this batch
            batch_number: Current batch number (1-indexed)
            total_batches: Total number of batches

        Returns:
            Notification object for this batch
        """
        category_details = self._build_category_details(batch_events)
        affected_users = self._get_affected_users(batch_events)

        events_by_category = {
            cat_value: len(events_list)
            for cat_value, events_list in category_details.items()
        }

        return ConsolidatedNotificationData(
            gear_name=gear_name,
            execution_timestamp=execution_timestamp,
            total_events=len(batch_events),
            events_by_category=events_by_category,
            event_summaries=[],  # Omit summaries in batches to save space
            affected_users=affected_users,
            affected_users_count=len(affected_users),
            category_details=category_details,
            batch_number=batch_number,
            total_batches=total_batches,
        )

    def create_batched_notifications(
        self, collector: UserEventCollector, gear_name: str
    ) -> List[ConsolidatedNotificationData]:
        """Create notification data, splitting into batches if needed.

        Args:
            collector: The UserEventCollector with categorized errors
            gear_name: Name of the gear that generated the errors

        Returns:
            List of ConsolidatedNotificationData, one per batch
        """
        # Create initial notification
        notification = self.create_notification_data(collector, gear_name)

        # Check if it fits within size limit
        size = notification.estimate_size()
        if size <= self.__max_template_data_bytes:
            log.info("Notification size %d bytes, sending as single email", size)
            return [notification]

        log.warning(
            "Notification size %d bytes exceeds limit, splitting into batches", size
        )

        # Flatten events from all categories
        grouped = collector.get_errors_by_category()
        all_events: List[tuple[EventCategory, UserProcessEvent]] = []
        for category, events in grouped.items():
            for event in events:
                all_events.append((category, event))

        # Split into batches
        batches = self._split_events_into_batches(
            all_events, gear_name, notification.execution_timestamp
        )

        log.info("Split notification into %d batches", len(batches))

        # Create notification for each batch
        notifications = []
        for i, batch_events in enumerate(batches, 1):
            batch_notification = self._create_batch_notification(
                gear_name,
                notification.execution_timestamp,
                batch_events,
                i,
                len(batches),
            )

            notifications.append(batch_notification)
            log.info(
                "Batch %d/%d: %d events, %d users, %d bytes",
                i,
                len(batches),
                len(batch_events),
                batch_notification.affected_users_count,
                batch_notification.estimate_size(),
            )

        return notifications

    def send_consolidated_notification(
        self,
        support_emails: List[str],
        notification_data: ConsolidatedNotificationData,
    ) -> Optional[str]:
        """Send consolidated error notification to support staff.

        Args:
            support_emails: List of support staff email addresses
            notification_data: The notification data to send

        Returns:
            Message ID if successfully sent, None otherwise
        """
        if not support_emails:
            log.warning("No support staff emails configured, skipping notification")
            return None

        destination = DestinationModel(to_addresses=support_emails)

        try:
            message_id = self.__email_client.send(
                configuration_set_name=self.__configuration_set_name,
                destination=destination,
                template="error-consolidated",
                template_data=notification_data,
            )

            batch_info = ""
            if notification_data.batch_number and notification_data.total_batches:
                batch_info = (
                    " (batch "
                    f"{notification_data.batch_number}/"
                    f"{notification_data.total_batches}"
                    ")"
                )

            log.info(
                "Sent consolidated error notification%s to %d recipients",
                batch_info,
                len(support_emails),
            )
            return message_id
        except Exception as error:
            log.error(
                "Failed to send consolidated error notification: %s",
                str(error),
            )
            return None

    def send_event_notification(
        self,
        collector: UserEventCollector,
        gear_name: str,
        support_emails: List[str],
    ) -> Optional[str]:
        """Send error notification at end of gear run.

        This is the main entry point for sending notifications from gears.
        Automatically handles batching if notification is too large.

        Args:
            collector: The UserEventCollector with categorized errors
            gear_name: Name of the gear that generated the errors
            support_emails: List of support staff email addresses

        Returns:
            Message ID of first notification if successfully sent, None otherwise
        """
        if not collector.has_errors():
            log.info("No errors to notify about")
            return None

        # Create batched notifications
        notifications = self.create_batched_notifications(collector, gear_name)

        if len(notifications) > 1:
            log.info("Sending %d batched notifications", len(notifications))

        # Send all batches
        first_message_id = None
        for notification in notifications:
            message_id = self.send_consolidated_notification(
                support_emails, notification
            )
            if first_message_id is None:
                first_message_id = message_id

        return first_message_id
