"""Mocked classes for event logging testing."""

from typing import List

from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent


class MockVisitEventLogger(VisitEventLogger):
    """Mock VisitEventLogger for testing."""

    def __init__(self):
        """Initialize mock logger."""
        self.logged_events: List[VisitEvent] = []

    def log_event(self, event: VisitEvent) -> None:
        """Record event for testing.

        Args:
            event: The event to log
        """
        self.logged_events.append(event)

    def clear(self) -> None:
        """Clear logged events."""
        self.logged_events.clear()

    def get_events_by_action(self, action: str) -> List[VisitEvent]:
        """Get all events with a specific action.

        Args:
            action: The action to filter by

        Returns:
            List of events with the specified action
        """
        return [e for e in self.logged_events if e.action == action]
