"""Module for handling user data from directory."""

import logging
from typing import Any, Dict, List

import yaml
from users.nacc_directory import UserEntry, UserEntryList

log = logging.getLogger(__name__)


def run(*, user_report: List[Dict[str, Any]]) -> str:
    """Converts user report records to UserDirectoryEntry and saves as list of
    dictionary objects to the project.

    Args:
      user_report: user report records
    """

    user_list = UserEntryList([])
    user_emails = set()
    for user_record in user_report:
        entry = UserEntry.create_from_record(user_record)
        if not entry:
            continue

        if entry.email in user_emails:
            log.warning("Email %s occurs in more than one contact", entry.email)

        user_list.append(entry)
        user_emails.add(entry.email)

    log.info("Creating directory file with %s entries", len(user_list))
    return yaml.safe_dump(
        data=user_list.model_dump(serialize_as_any=True),
        allow_unicode=True,
        default_flow_style=False,
    )
