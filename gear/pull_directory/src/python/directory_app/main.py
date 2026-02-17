"""Module for handling user data from directory."""

import logging
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)
from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import UserEntryList

log = logging.getLogger(__name__)


def run(
    *, user_report: List[Dict[str, Any]], collector: Optional[UserEventCollector] = None
) -> str:
    """Converts user report records to UserDirectoryEntry and saves as list of
    dictionary objects to the project.

    Args:
      user_report: user report records
      collector: optional event collector for error tracking
    """
    if collector is None:
        collector = UserEventCollector()

    user_list = UserEntryList([])
    user_emails = set()
    for user_record in user_report:
        try:
            dir_record = DirectoryAuthorizations.model_validate(
                user_record, by_alias=True
            )
        except ValidationError as error:
            log.error("Error loading user record: %s", error)

            # Create error event for validation failure
            email = user_record.get("email", "unknown")
            firstname = user_record.get("firstname", "")
            lastname = user_record.get("lastname", "")
            name = (
                f"{firstname} {lastname}".strip()
                if firstname or lastname
                else "Unknown"
            )
            auth_email = user_record.get("fw_email", "")
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.MISSING_DIRECTORY_DATA,
                user_context=UserContext(email=email, name=name, auth_email=auth_email),
                message="Directory record validation failed",
                action_needed="check_directory_record_format",
            )
            collector.collect(error_event)
            continue

        if not dir_record.permissions_approval:
            log.warning("Ignoring %s: Permissions not approved", dir_record.email)

            # Create error event for missing permissions approval
            name = f"{dir_record.firstname} {dir_record.lastname}".strip()
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.MISSING_DIRECTORY_PERMISSIONS,
                user_context=UserContext(
                    email=dir_record.email,
                    name=name,
                    center_id=dir_record.adcid,
                    auth_email=dir_record.auth_email,
                ),
                message="User permissions not approved in directory",
                action_needed="contact_center_administrator_for_approval",
            )
            collector.collect(error_event)
            continue

        if not dir_record.complete:
            log.warning(
                "Ignoring %s: Data platform survey is incomplete", dir_record.email
            )

            # Create error event for incomplete survey
            name = f"{dir_record.firstname} {dir_record.lastname}".strip()
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.MISSING_DIRECTORY_PERMISSIONS,
                user_context=UserContext(
                    email=dir_record.email,
                    name=name,
                    center_id=dir_record.adcid,
                    auth_email=dir_record.auth_email,
                ),
                message="Data platform survey is incomplete",
                action_needed="complete_data_platform_survey",
            )
            collector.collect(error_event)
            continue

        entry = dir_record.to_user_entry()
        if not entry:
            continue

        if entry.email in user_emails:
            log.warning("Email %s occurs in more than one contact", entry.email)

        user_list.append(entry)
        user_emails.add(entry.email)

    log.info("Creating directory file with %s entries", len(user_list))
    return yaml.safe_dump(
        data=user_list.model_dump(serialize_as_any=True, exclude_none=True),
        allow_unicode=True,
        default_flow_style=False,
    )
