"""Data models for the Transactional Event Scraper."""

from datetime import datetime
from typing import Optional

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import QCStatus, VisitMetadata
from pydantic import BaseModel, ConfigDict, Field


class EventData(BaseModel):
    """Intermediate data structure for extracted event information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)  # Allow FileEntry

    log_file: FileEntry
    visit_metadata: VisitMetadata
    qc_status: Optional[QCStatus]
    submission_timestamp: datetime
    qc_completion_timestamp: Optional[datetime]


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
