"""Error models for user access issues."""

import uuid
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
    """Simple error collector that accumulates errors during gear execution."""

    def __init__(self):
        """Initialize an empty error collector."""
        self._errors: List[ErrorEvent] = []

    def collect(self, event: ErrorEvent) -> None:
        """Add an error event to the collection.

        Args:
            event: The error event to add to the collection
        """
        self._errors.append(event)

    def get_errors(self) -> List[ErrorEvent]:
        """Get all collected errors.

        Returns:
            A copy of the list of collected error events
        """
        return self._errors.copy()

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
        """Get the number of collected errors.

        Returns:
            The number of error events in the collection
        """
        return len(self._errors)
