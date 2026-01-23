"""Notification generation and template system for error handling."""

import logging
from datetime import datetime
from typing import ClassVar, Dict, List, Optional

from notifications.email import BaseTemplateModel, DestinationModel, EmailClient

from users.error_models import ErrorCategory, ErrorCollector

log = logging.getLogger(__name__)


class ConsolidatedNotificationData(BaseTemplateModel):
    """Template data model for consolidated error notifications.

    Extends BaseTemplateModel to work with existing AWS SES template
    infrastructure.
    """

    gear_name: str
    execution_timestamp: str
    total_errors: int
    errors_by_category: Dict[str, int]
    error_summaries: List[str]
    affected_users: List[str]

    # Optional fields for specific error categories
    unclaimed_records: Optional[List[Dict[str, str]]] = None
    email_mismatches: Optional[List[Dict[str, str]]] = None
    unverified_emails: Optional[List[Dict[str, str]]] = None
    incomplete_claims: Optional[List[Dict[str, str]]] = None
    bad_orcid_claims: Optional[List[Dict[str, str]]] = None
    missing_directory_permissions: Optional[List[Dict[str, str]]] = None
    missing_directory_data: Optional[List[Dict[str, str]]] = None
    missing_registry_data: Optional[List[Dict[str, str]]] = None
    insufficient_permissions: Optional[List[Dict[str, str]]] = None
    duplicate_user_records: Optional[List[Dict[str, str]]] = None
    flywheel_errors: Optional[List[Dict[str, str]]] = None


class ErrorNotificationGenerator:
    """Generates notifications for error events using AWS SES templates."""

    # Template name mapping for each error category
    CATEGORY_TEMPLATES: ClassVar[Dict[ErrorCategory, str]] = {
        ErrorCategory.UNCLAIMED_RECORDS: "error-unclaimed-records",
        ErrorCategory.EMAIL_MISMATCH: "error-email-mismatch",
        ErrorCategory.UNVERIFIED_EMAIL: "error-unverified-email",
        ErrorCategory.INCOMPLETE_CLAIM: "error-incomplete-claim",
        ErrorCategory.BAD_ORCID_CLAIMS: "error-bad-orcid-claims",
        ErrorCategory.MISSING_DIRECTORY_PERMISSIONS: (
            "error-missing-directory-permissions"
        ),
        ErrorCategory.MISSING_DIRECTORY_DATA: "error-missing-directory-data",
        ErrorCategory.MISSING_REGISTRY_DATA: "error-missing-registry-data",
        ErrorCategory.INSUFFICIENT_PERMISSIONS: "error-insufficient-permissions",
        ErrorCategory.DUPLICATE_USER_RECORDS: "error-duplicate-user-records",
        ErrorCategory.FLYWHEEL_ERROR: "error-flywheel-error",
    }

    def __init__(self, email_client: EmailClient, configuration_set_name: str):
        """Initialize the error notification generator.

        Args:
            email_client: The EmailClient instance for sending notifications
            configuration_set_name: The AWS SES configuration set name
        """
        self.__email_client = email_client
        self.__configuration_set_name = configuration_set_name

    def select_template(self, category: ErrorCategory) -> str:
        """Select the appropriate SES template for an error category.

        Args:
            category: The error category

        Returns:
            The SES template name for the category
        """
        return self.CATEGORY_TEMPLATES.get(category, "error-generic")

    def create_notification_data(
        self, error_collector: ErrorCollector, gear_name: str
    ) -> ConsolidatedNotificationData:
        """Create template data for consolidated notification.

        Args:
            error_collector: The ErrorCollector with categorized errors
            gear_name: Name of the gear that generated the errors

        Returns:
            ConsolidatedNotificationData ready for template rendering
        """
        # Get errors grouped by category from the collector
        grouped = error_collector.get_errors_by_category()

        # Create category-specific data
        category_data = {}

        for category, category_errors in grouped.items():
            error_list = []
            for error in category_errors:
                error_dict = {
                    "email": error.user_context.email,
                    "name": (
                        error.user_context.name.as_str()
                        if error.user_context.name
                        else "Unknown"
                    ),
                    "message": error.error_details.get("message", "No details"),
                    "timestamp": error.timestamp.isoformat(),
                }

                # Add category-specific fields
                if error.user_context.registry_id:
                    error_dict["registry_id"] = error.user_context.registry_id
                if error.user_context.auth_email:
                    error_dict["auth_email"] = error.user_context.auth_email
                if error.user_context.center_id:
                    error_dict["center_id"] = str(error.user_context.center_id)

                # Add action needed if present
                action_needed = error.error_details.get("action_needed")
                if action_needed:
                    error_dict["action_needed"] = action_needed

                error_list.append(error_dict)

            # Map category to field name
            field_name = self._category_to_field_name(category)
            category_data[field_name] = error_list

        # Get all errors as flat list for summaries
        all_errors = error_collector.get_errors()

        return ConsolidatedNotificationData(
            gear_name=gear_name,
            execution_timestamp=datetime.now().isoformat(),
            total_errors=error_collector.error_count(),
            errors_by_category=error_collector.count_by_category(),
            error_summaries=[error.to_summary() for error in all_errors],
            affected_users=error_collector.get_affected_users(),
            **category_data,
        )

    def _category_to_field_name(self, category: ErrorCategory) -> str:
        """Convert error category to field name for template data.

        Args:
            category: The error category

        Returns:
            Field name for the category in template data
        """
        mapping = {
            ErrorCategory.UNCLAIMED_RECORDS: "unclaimed_records",
            ErrorCategory.EMAIL_MISMATCH: "email_mismatches",
            ErrorCategory.UNVERIFIED_EMAIL: "unverified_emails",
            ErrorCategory.INCOMPLETE_CLAIM: "incomplete_claims",
            ErrorCategory.BAD_ORCID_CLAIMS: "bad_orcid_claims",
            ErrorCategory.MISSING_DIRECTORY_PERMISSIONS: (
                "missing_directory_permissions"
            ),
            ErrorCategory.MISSING_DIRECTORY_DATA: "missing_directory_data",
            ErrorCategory.MISSING_REGISTRY_DATA: "missing_registry_data",
            ErrorCategory.INSUFFICIENT_PERMISSIONS: "insufficient_permissions",
            ErrorCategory.DUPLICATE_USER_RECORDS: "duplicate_user_records",
            ErrorCategory.FLYWHEEL_ERROR: "flywheel_errors",
        }
        return mapping.get(category, "unknown_errors")

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

    def send_error_notification(
        self,
        error_collector: ErrorCollector,
        gear_name: str,
        support_emails: List[str],
    ) -> Optional[str]:
        """Send error notification at end of gear run.

        This is the main entry point for sending notifications from gears.

        Args:
            error_collector: The ErrorCollector with categorized errors
            gear_name: Name of the gear that generated the errors
            support_emails: List of support staff email addresses

        Returns:
            Message ID if successfully sent, None otherwise
        """
        if not error_collector.has_errors():
            log.info("No errors to notify about")
            return None

        notification_data = self.create_notification_data(error_collector, gear_name)
        return self.send_consolidated_notification(support_emails, notification_data)
