"""Error models for user access issues."""

import uuid
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from users.user_entry import PersonName, UserEntry


class ErrorCategory(Enum):
    """Enumeration of error categories for user access issues."""

    UNCLAIMED_RECORDS = "Unclaimed Records"
    EMAIL_MISMATCH = "Authentication Email Mismatch"
    UNVERIFIED_EMAIL = "Unverified Email"
    INCOMPLETE_CLAIM = "Incomplete Claim"
    BAD_ORCID_CLAIMS = "Bad ORCID Claims"
    MISSING_DIRECTORY_PERMISSIONS = "Missing Directory Permissions"
    MISSING_DIRECTORY_DATA = "Missing Directory Data"
    MISSING_REGISTRY_DATA = "Missing Registry Data"
    INSUFFICIENT_PERMISSIONS = "Insufficient Permissions"
    DUPLICATE_USER_RECORDS = "Duplicate/Wrong User Records"
    FLYWHEEL_ERROR = "Flywheel Error"


class UserContext(BaseModel):
    """User context information for error events."""

    email: str
    name: Optional[PersonName] = None
    center_id: Optional[int] = None
    registry_id: Optional[str] = None
    auth_email: Optional[str] = None

    @classmethod
    def from_user_entry(cls, entry: UserEntry) -> "UserContext":
        """Create UserContext from a UserEntry object.

        Args:
            entry: The user entry to extract context from

        Returns:
            UserContext with information from the user entry
        """
        return cls(email=entry.email, name=entry.name, auth_email=entry.auth_email)


class ErrorEvent(BaseModel):
    """Represents an error event in the system."""

    model_config = ConfigDict(use_enum_values=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    category: ErrorCategory
    user_context: UserContext
    error_details: Dict[str, Any]

    def to_summary(self) -> str:
        """Convert error event to a one-line summary for notifications.

        Returns:
            A formatted summary string
        """
        message = self.error_details.get("message", "No details")
        # Since use_enum_values=True, category is already a string
        return f"{self.category}: {self.user_context.email} - {message}"


class ErrorCollector:
    """Error collector that accumulates and categorizes errors during gear
    execution."""

    def __init__(self):
        """Initialize an empty error collector."""
        self._errors: Dict[ErrorCategory, List[ErrorEvent]] = defaultdict(list)

    def collect(self, event: ErrorEvent) -> None:
        """Add an error event to the collection, automatically categorizing it.

        Args:
            event: The error event to add to the collection
        """
        # Convert string category back to enum if needed
        if isinstance(event.category, str):
            category_enum = next(
                (cat for cat in ErrorCategory if cat.value == event.category),
                None,
            )
            if category_enum:
                self._errors[category_enum].append(event)
        else:
            self._errors[event.category].append(event)

    def get_errors(self) -> List[ErrorEvent]:
        """Get all collected errors as a flat list.

        Returns:
            A list of all collected error events
        """
        all_errors = []
        for error_list in self._errors.values():
            all_errors.extend(error_list)
        return all_errors

    def get_errors_by_category(self) -> Dict[ErrorCategory, List[ErrorEvent]]:
        """Get errors grouped by category.

        Returns:
            Dictionary mapping error category to list of error events
        """
        return dict(self._errors)

    def get_errors_for_category(self, category: ErrorCategory) -> List[ErrorEvent]:
        """Get all errors for a specific category.

        Args:
            category: The error category to retrieve

        Returns:
            List of error events for the specified category
        """
        return self._errors.get(category, []).copy()

    def count_by_category(self) -> Dict[str, int]:
        """Count errors by category.

        Returns:
            Dictionary mapping category name (string) to count
        """
        return {
            category.value: len(errors) for category, errors in self._errors.items()
        }

    def get_affected_users(self) -> List[str]:
        """Get list of unique user emails affected by errors.

        Returns:
            List of unique user email addresses
        """
        users = set()
        for error_list in self._errors.values():
            for error in error_list:
                users.add(error.user_context.email)
        return list(users)

    def clear(self) -> None:
        """Clear all collected errors."""
        self._errors.clear()

    def has_errors(self) -> bool:
        """Check if there are any collected errors.

        Returns:
            True if there are errors, False otherwise
        """
        return len(self._errors) > 0

    def error_count(self) -> int:
        """Get the total number of collected errors.

        Returns:
            The total number of error events in the collection
        """
        return sum(len(errors) for errors in self._errors.values())
