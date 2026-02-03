"""Data models for the Transactional Event Scraper.

This module provides data models used in the transactional event scraping
process, including:

- EventMatchKey: Key for matching submit events with QC events based on
  ptid, date, and module
- EventData: Base class for event data extracted from files
- QCEventData: Data extracted from JSON files for QC event creation
- SubmitEventData: Data extracted from QC logs for submit event creation
- DateRange: Configuration for filtering files by date range
- UnmatchedSubmitEvents: Collection for managing unmatched submit events
  with efficient O(1) lookup

The matching process uses EventMatchKey to correlate submit events (from
QC status logs) with QC events (from form JSON files), enabling enrichment
of submit events with packet information and other metadata.
"""

from datetime import datetime
from typing import Dict, List, Optional

from nacc_common.error_models import QCStatus, VisitMetadata
from pydantic import BaseModel, Field, field_validator

from event_capture.visit_events import VisitEvent


class EventMatchKey(BaseModel):
    """Key for matching submit events with QC events.

    Uses only fields guaranteed to be in QC status log filename. Module
    is automatically normalized to uppercase for case-insensitive
    matching.

    The matching strategy is based on the constraint that QC status log
    filenames follow a specific pattern that includes ptid, date, and module,
    but NOT packet or visit number. Therefore, we can only reliably match
    events using these three fields.

    Example QC log filename: "NACC123456_2024-01-15_UDS_qc-status.log"
    - ptid: NACC123456
    - date: 2024-01-15
    - module: UDS (normalized to uppercase)

    The EventMatchKey is hashable and can be used as a dictionary key for
    efficient O(1) lookup during the matching process.
    """

    ptid: str
    date: str  # visit date
    module: str

    @field_validator("module")
    @classmethod
    def normalize_module(cls, v: str) -> str:
        """Normalize module to uppercase for case-insensitive matching.

        This ensures that "UDS", "uds", and "Uds" all match the same event.
        Module names in QC logs and JSON files may have inconsistent casing,
        so normalization is essential for reliable matching.

        Args:
            v: The module value

        Returns:
            Module normalized to uppercase
        """
        return v.upper() if v else ""

    @classmethod
    def from_visit_metadata(cls, metadata: VisitMetadata) -> "EventMatchKey":
        """Create match key from visit metadata.

        Extracts the matching fields (ptid, date, module) from visit metadata
        and creates an EventMatchKey. This is used when processing both submit
        events (from QC logs) and QC events (from JSON files) to create
        comparable keys for matching.

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

        # Module normalization is handled by field validator
        return cls(
            ptid=metadata.ptid,
            date=metadata.date,
            module=metadata.module,
        )

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
        # Create a match key from the submit event's identifying fields.
        # The key uses ptid, date (as string), and module (normalized to uppercase).
        # This key will be used for O(1) lookup when matching with QC events.
        # Module normalization is handled by EventMatchKey validator.
        key = EventMatchKey(
            ptid=event.ptid, date=event.visit_date, module=event.module or ""
        )
        # Store the event in a dictionary keyed by the match key.
        # This enables efficient O(1) lookup during the matching phase.
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
        # Use dict.pop() to atomically lookup and remove the event.
        # This ensures that each submit event can only be matched once,
        # preventing duplicate event captures even if multiple QC events
        # have the same match key.
        # Returns None if the key is not found (no matching submit event).
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
