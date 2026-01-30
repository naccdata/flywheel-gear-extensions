"""Data models for the Transactional Event Scraper."""

from datetime import datetime
from typing import Dict, List, Optional

from nacc_common.error_models import QCStatus, VisitMetadata
from pydantic import BaseModel, Field

from event_capture.visit_events import VisitEvent


class EventMatchKey(BaseModel):
    """Key for matching submit events with QC events.

    Uses only fields guaranteed to be in QC status log filename.
    """

    ptid: str
    date: str  # visit date
    module: str

    @classmethod
    def from_visit_metadata(cls, metadata: VisitMetadata) -> "EventMatchKey":
        """Create match key from visit metadata.

        Args:
            metadata: The visit metadata to extract key fields from

        Returns:
            EventMatchKey instance

        Raises:
            ValueError: If required fields (ptid, date, module) are missing
        """
        if not metadata.ptid:
            raise ValueError("ptid is required for EventMatchKey")
        if not metadata.date:
            raise ValueError("date is required for EventMatchKey")
        if not metadata.module:
            raise ValueError("module is required for EventMatchKey")

        return cls(ptid=metadata.ptid, date=metadata.date, module=metadata.module)

    def __hash__(self) -> int:
        """Make EventMatchKey hashable for use as dict key."""
        return hash((self.ptid, self.date, self.module))

    def __eq__(self, other: object) -> bool:
        """Compare EventMatchKey instances for equality."""
        if not isinstance(other, EventMatchKey):
            return NotImplemented
        return (
            self.ptid == other.ptid
            and self.date == other.date
            and self.module == other.module
        )


class EventData(BaseModel):
    visit_metadata: VisitMetadata


class QCEventData(EventData):
    """Data extracted from JSON file for QC event creation."""

    qc_status: QCStatus  # From QC status log
    qc_completion_timestamp: datetime  # From QC status log modified time


class SubmitEventData(EventData):
    """Intermediate data structure for extracted event information."""

    submission_timestamp: datetime


class ProcessingStatistics(BaseModel):
    """Statistics from the processing operation."""

    files_processed: int = Field(
        default=0, ge=0, description="Number of files processed"
    )
    submission_events_created: int = Field(
        default=0, ge=0, description="Number of submission events created"
    )
    pass_qc_events_created: int = Field(
        default=0, ge=0, description="Number of pass-qc events created"
    )
    errors_encountered: int = Field(
        default=0, ge=0, description="Number of errors encountered"
    )
    skipped_files: int = Field(default=0, ge=0, description="Number of files skipped")


class DateRange(BaseModel):
    """Optional configuration for filtering files by date."""

    start_date: Optional[datetime] = Field(
        default=None, description="Start date for filtering files"
    )
    end_date: Optional[datetime] = Field(
        default=None, description="End date for filtering files"
    )

    def includes_file(self, file_timestamp: datetime) -> bool:
        """Check if file timestamp falls within the date range.

        Args:
            file_timestamp: The timestamp to check

        Returns:
            True if the timestamp falls within the range, False otherwise
        """
        return not (
            (self.start_date and file_timestamp < self.start_date)
            or (self.end_date and file_timestamp > self.end_date)
        )


class UnmatchedSubmitEvents:
    """Manages unmatched submit events with efficient lookup by match key.

    This class stores submit events that have not yet been matched with
    corresponding QC events. Events are keyed by EventMatchKey (ptid,
    date, module) for efficient O(1) lookup during the matching process.
    """

    def __init__(self) -> None:
        """Initialize the unmatched events collection."""
        self._events: Dict[EventMatchKey, VisitEvent] = {}

    def add(self, event: VisitEvent) -> None:
        """Add an unmatched submit event to the collection.

        Args:
            event: The submit event to add

        Raises:
            ValueError: If required fields for creating match key are missing
        """
        key = EventMatchKey(
            ptid=event.ptid, date=event.visit_date, module=event.module or ""
        )
        self._events[key] = event

    def find_and_remove(self, key: EventMatchKey) -> Optional[VisitEvent]:
        """Find and remove a submit event by match key.

        This method removes the event from the collection, ensuring that
        subsequent calls with the same key will return None (preventing
        duplicate matches).

        Args:
            key: The match key to search for

        Returns:
            The matched submit event, or None if not found
        """
        return self._events.pop(key, None)

    def get_remaining(self) -> List[VisitEvent]:
        """Get all remaining unmatched submit events.

        Returns:
            List of all unmatched submit events still in the collection
        """
        return list(self._events.values())

    def count(self) -> int:
        """Get count of unmatched submit events.

        Returns:
            Number of unmatched submit events in the collection
        """
        return len(self._events)
