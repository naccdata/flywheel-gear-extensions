"""Event models for user process events (both successes and errors)."""

import uuid
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_serializer,
)

from users.user_entry import PersonName, UserEntry


class EventType(Enum):
    """Type of user process event."""

    SUCCESS = "success"
    ERROR = "error"


class EventCategory(Enum):
    """Enumeration of event categories for user process events."""

    # Success category
    USER_CREATED = "User Successfully Created"

    # Error categories
    UNCLAIMED_RECORDS = "Unclaimed Records"
    INCOMPLETE_CLAIM = "Incomplete Claims"
    BAD_ORCID_CLAIMS = "Bad ORCID Claims"
    MISSING_DIRECTORY_PERMISSIONS = "Missing Directory Permissions"
    MISSING_DIRECTORY_DATA = "Missing Directory Data"
    MISSING_REGISTRY_DATA = "Missing Registry Data"
    INSUFFICIENT_PERMISSIONS = "Insufficient Permissions"
    DUPLICATE_USER_RECORDS = "Duplicate/Wrong User Records"
    FLYWHEEL_ERROR = "Flywheel Errors"

    def to_field_name(self) -> str:
        """Convert category to template field name (snake_case).

        Returns:
            Snake-case field name for use in templates

        Example:
            EventCategory.UNCLAIMED_RECORDS.to_field_name() -> "unclaimed_records"
        """
        return self.value.lower().replace(" ", "_").replace("/", "_")


class UserContext(BaseModel):
    """User context information for events."""

    email: str
    name: str = "Unknown"
    center_id: Optional[int] = None
    registry_id: Optional[str] = None
    auth_email: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def convert_person_name(cls, value):
        """Convert PersonName objects to strings.

        This allows PersonName objects to be passed in for backward
        compatibility, but stores them as strings internally.
        """
        if value is None:
            return "Unknown"
        # Check if it's a PersonName object
        if isinstance(value, PersonName):
            return value.as_str()
        # If it's already a string, return as-is
        if isinstance(value, str):
            return value.strip()
        # If it's a dict (from deserialization), convert to string
        if isinstance(value, dict) and "first_name" in value and "last_name" in value:
            full_name = f"{value['first_name']} {value['last_name']}".strip()
            return full_name if full_name else "Unknown"
        return "Unknown"

    @field_serializer("center_id", mode="plain")
    def serialize_center_id(self, center_id: Optional[int]) -> Optional[str]:
        """Serialize center_id as a string for templates.

        Templates need string values, so convert the int to string
        during serialization.
        """
        return str(center_id) if center_id is not None else None

    @classmethod
    def from_user_entry(cls, entry: UserEntry) -> "UserContext":
        """Create UserContext from a UserEntry object.

        Args:
            entry: The user entry to extract context from

        Returns:
            UserContext with information from the user entry
        """
        # Extract center_id from adcid if available (ActiveUserEntry)
        center_id = None
        if hasattr(entry, "adcid"):
            center_id = entry.adcid

        # Extract registry_id if available (RegisteredUserEntry)
        registry_id = None
        if hasattr(entry, "registry_id"):
            registry_id = entry.registry_id

        return cls(
            email=entry.email,
            name=entry.name.as_str() if entry.name else None,
            auth_email=entry.auth_email,
            center_id=center_id,
            registry_id=registry_id,
        )


class UserProcessEvent(BaseModel):
    """Represents an event in the user process system (success or error)."""

    model_config = ConfigDict(use_enum_values=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: EventType
    category: EventCategory
    user_context: UserContext
    message: str
    action_needed: Optional[str] = None

    @classmethod
    def csv_fieldnames(cls) -> List[str]:
        """Returns the field names for CSV export in the correct order.

        The CSV export flattens the user_context fields, so this method
        returns the flattened field names in the order they should appear
        in the CSV.

        Returns:
            List of field names for CSV export
        """
        return [
            "email",
            "name",
            "center_id",
            "registry_id",
            "auth_email",
            "category",
            "message",
            "action_needed",
            "timestamp",
            "event_id",
        ]

    def to_summary(self) -> str:
        """Convert event to a one-line summary for notifications.

        Returns:
            A formatted summary string
        """
        # Since use_enum_values=True, category is already a string
        return f"{self.category}: {self.user_context.email} - {self.message}"

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime) -> str:
        return timestamp.isoformat()

    @field_serializer("category")
    def serialize_category(self, category: EventCategory) -> str:
        if isinstance(category, str):
            return category
        return category.to_field_name()

    @model_serializer(mode="wrap")
    def serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        data = handler(self)

        context = data.pop("user_context")
        for k, v in context.items():
            data[k] = v

        return data

    def is_success(self) -> bool:
        """Check if this is a success event.

        Returns:
            True if this is a success event, False otherwise
        """
        return (
            self.event_type == EventType.SUCCESS.value
            if isinstance(self.event_type, str)
            else self.event_type == EventType.SUCCESS
        )

    def is_error(self) -> bool:
        """Check if this is an error event.

        Returns:
            True if this is an error event, False otherwise
        """
        return (
            self.event_type == EventType.ERROR.value
            if isinstance(self.event_type, str)
            else self.event_type == EventType.ERROR
        )


class UserEventCollector:
    """Event collector that accumulates and categorizes events during gear
    execution.

    Collects both success and error events, maintaining them separately
    for easy reporting.
    """

    def __init__(self):
        """Initialize an empty event collector."""
        self._events: Dict[EventCategory, List[UserProcessEvent]] = defaultdict(list)

    def collect(self, event: UserProcessEvent) -> None:
        """Add an event to the collection, automatically categorizing it.

        Args:
            event: The event to add to the collection
        """
        # Convert string category back to enum if needed
        if isinstance(event.category, str):
            category_enum = next(
                (cat for cat in EventCategory if cat.value == event.category),
                None,
            )
            if category_enum:
                self._events[category_enum].append(event)
        else:
            self._events[event.category].append(event)

    def get_events(self) -> List[UserProcessEvent]:
        """Get all collected events as a flat list.

        Returns:
            A list of all collected events
        """
        all_events = []
        for event_list in self._events.values():
            all_events.extend(event_list)
        return all_events

    def get_errors(self) -> List[UserProcessEvent]:
        """Get all error events.

        Returns:
            A list of all error events
        """
        return [event for event in self.get_events() if event.is_error()]

    def get_successes(self) -> List[UserProcessEvent]:
        """Get all success events.

        Returns:
            A list of all success events
        """
        return [event for event in self.get_events() if event.is_success()]

    def get_events_by_category(self) -> Dict[EventCategory, List[UserProcessEvent]]:
        """Get events grouped by category.

        Returns:
            Dictionary mapping event category to list of events
        """
        return dict(self._events)

    def get_errors_by_category(self) -> Dict[EventCategory, List[UserProcessEvent]]:
        """Get error events grouped by category.

        Returns:
            Dictionary mapping error category to list of error events
        """
        return {
            category: events
            for category, events in self._events.items()
            if events and events[0].is_error()
        }

    def get_events_for_category(
        self, category: EventCategory
    ) -> List[UserProcessEvent]:
        """Get all events for a specific category.

        Args:
            category: The event category to retrieve

        Returns:
            List of events for the specified category
        """
        return self._events.get(category, []).copy()

    def count_by_category(self) -> Dict[str, int]:
        """Count events by category.

        Returns:
            Dictionary mapping category name (string) to count
        """
        return {
            category.value: len(events) for category, events in self._events.items()
        }

    def get_affected_users(self) -> List[str]:
        """Get list of unique user emails affected by events.

        Returns:
            List of unique user email addresses
        """
        users = set()
        for event_list in self._events.values():
            for event in event_list:
                users.add(event.user_context.email)
        return list(users)

    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()

    def has_errors(self) -> bool:
        """Check if there are any error events.

        Returns:
            True if there are errors, False otherwise
        """
        return len(self.get_errors()) > 0

    def has_successes(self) -> bool:
        """Check if there are any success events.

        Returns:
            True if there are successes, False otherwise
        """
        return len(self.get_successes()) > 0

    def has_events(self) -> bool:
        """Check if there are any collected events.

        Returns:
            True if there are events, False otherwise
        """
        return len(self._events) > 0

    def error_count(self) -> int:
        """Get the total number of error events.

        Returns:
            The total number of error events in the collection
        """
        return len(self.get_errors())

    def success_count(self) -> int:
        """Get the total number of success events.

        Returns:
            The total number of success events in the collection
        """
        return len(self.get_successes())

    def event_count(self) -> int:
        """Get the total number of collected events.

        Returns:
            The total number of events in the collection
        """
        return sum(len(events) for events in self._events.values())
