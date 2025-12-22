"""Mock event logging components for testing."""

from unittest.mock import Mock

from event_logging.event_logger import VisitEventLogger
from event_logging.visit_events import VisitEvent


class MockVisitEventLogger(VisitEventLogger):
    """Mock VisitEventLogger for testing.

    Stores logged events in a list for verification in tests.
    """

    def __init__(self):
        self.logged_events: list[VisitEvent] = []

    def log_event(self, event: VisitEvent) -> None:
        """Mock log_event that stores events."""
        self.logged_events.append(event)

    def clear_events(self) -> None:
        """Clear all logged events."""
        self.logged_events.clear()

    def clear(self) -> None:
        """Alias for clear_events() for compatibility with existing tests."""
        self.clear_events()

    def get_events_count(self) -> int:
        """Get the number of logged events."""
        return len(self.logged_events)

    def get_last_event(self) -> VisitEvent:
        """Get the most recently logged event."""
        if not self.logged_events:
            raise IndexError("No events have been logged")
        return self.logged_events[-1]

    def get_events_by_action(self, action: str) -> list[VisitEvent]:
        """Get all events with the specified action."""
        return [event for event in self.logged_events if event.action == action]


def create_mock_event_logger() -> Mock:
    """Create a basic mock event logger for simple tests."""
    return Mock(spec=VisitEventLogger)


def create_failing_mock_event_logger(
    error_message: str = "Mock event logging failure",
) -> Mock:
    """Create a mock event logger that always fails."""
    mock_logger = Mock(spec=VisitEventLogger)
    mock_logger.log_event.side_effect = RuntimeError(error_message)
    return mock_logger
