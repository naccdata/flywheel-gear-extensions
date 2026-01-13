"""Mock event logging components for testing."""

from unittest.mock import Mock

from event_capture.event_logger import VisitEventCapture
from event_capture.visit_events import VisitEvent


class MockVisitEventCapture(VisitEventCapture):
    """Mock VisitEventCapture for testing.

    Stores logged events in a list for verification in tests.
    """

    def __init__(self):
        self.logged_events: list[VisitEvent] = []

    def capture_event(self, event: VisitEvent) -> None:
        """Mock capture_event that stores events."""
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


def create_mock_event_capture() -> Mock:
    """Create a basic mock event logger for simple tests."""
    return Mock(spec=VisitEventCapture)


def create_failing_mock_event_capture(
    error_message: str = "Mock event logging failure",
) -> Mock:
    """Create a mock event logger that always fails."""
    mock_logger = Mock(spec=VisitEventCapture)
    mock_logger.capture_event.side_effect = RuntimeError(error_message)
    return mock_logger
