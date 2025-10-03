"""Module for handling user data from directory."""

import logging
from typing import Any, Dict, List

import yaml
from pydantic import ValidationError
from users.nacc_directory import DirectoryAuthorizations
from users.user_entry import UserEntryList

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
        try:
            dir_record = DirectoryAuthorizations.model_validate(
                user_record, by_alias=True
            )
        except ValidationError as error:
            log.error("Error loading user record: %s", error)
            continue

        if not dir_record.permissions_approval:
            log.warning("Ignoring %s: Permissions not approved", dir_record.email)
            continue
        if not dir_record.complete:
            log.warning(
                "Ignoring %s: Data platform survey is incomplete", dir_record.email
            )
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
