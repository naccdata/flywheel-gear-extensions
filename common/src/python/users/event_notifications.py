"""Notification generation and template system for error handling."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from notifications.email import BaseTemplateModel, DestinationModel, EmailClient
from pydantic import SerializationInfo, SerializerFunctionWrapHandler, model_serializer
from users.event_models import UserEventCollector

log = logging.getLogger(__name__)


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


class UserEventNotificationGenerator:
    """Generates notifications for error events using AWS SES templates.

    Uses a single consolidated template (error-consolidated) that
    includes all error categories in one email notification.
    """

    def __init__(self, email_client: EmailClient, configuration_set_name: str):
        """Initialize the error notification generator.

        Args:
            email_client: The EmailClient instance for sending notifications
            configuration_set_name: The AWS SES configuration set name
        """
        self.__email_client = email_client
        self.__configuration_set_name = configuration_set_name

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
            log.info(
                "Sent consolidated error notification to %d recipients",
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

        Args:
            collector: The UserEventCollector with categorized errors
            gear_name: Name of the gear that generated the errors
            support_emails: List of support staff email addresses

        Returns:
            Message ID if successfully sent, None otherwise
        """
        if not collector.has_errors():
            log.info("No errors to notify about")
            return None

        notification_data = self.create_notification_data(collector, gear_name)
        return self.send_consolidated_notification(support_emails, notification_data)
