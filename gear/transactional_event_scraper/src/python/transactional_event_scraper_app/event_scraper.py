"""EventScraper orchestrator for discovering and processing QC status log
files."""

import logging
from typing import Optional

from event_capture.event_capture import VisitEventCapture
from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor

from transactional_event_scraper_app.event_generator import EventGenerator
from transactional_event_scraper_app.log_file_processor import extract_event_from_log
from transactional_event_scraper_app.models import DateRange, ProcessingStatistics

log = logging.getLogger(__name__)


class EventScraper:
    """Main orchestrator that coordinates file discovery and processing."""

    def __init__(
        self,
        project: ProjectAdaptor,
        event_capture: Optional[VisitEventCapture] = None,
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None,
    ) -> None:
        """Initialize the EventScraper.

        Args:
            project: The project adaptor for accessing project files
            event_capture: Optional event capture for storing events (None for dry-run)
            dry_run: Whether to perform a dry run without capturing events
            date_filter: Optional date range for filtering files
        """
        self._project = project
        self._event_capture = event_capture
        self._dry_run = dry_run
        self._date_filter = date_filter
        self._event_generator = EventGenerator(project)

    def scrape_events(self) -> ProcessingStatistics:
        """Discover and process all QC status log files in the project.

        Returns:
            ProcessingStatistics with summary of processing results
        """
        stats = ProcessingStatistics()

        # Discover all QC status log files in the project
        log_files = self._discover_log_files()
        log.info(f"Discovered {len(log_files)} QC status log files")

        # Process each log file
        for log_file in log_files:
            try:
                self._process_log_file(log_file, stats)
            except Exception as error:
                # Continue processing remaining files on individual failures
                log.error(f"Error processing {log_file.name}: {error}", exc_info=True)
                stats.errors_encountered += 1
                continue

        # Log summary statistics
        self._log_summary(stats)

        return stats

    def _process_log_file(self, log_file, stats: ProcessingStatistics) -> None:
        """Process a single log file and update statistics.

        Args:
            log_file: The log file to process
            stats: Statistics object to update
        """
        # Apply date filter if configured
        if self._date_filter and not self._date_filter.includes_file(log_file.created):
            log.debug(
                f"Skipping {log_file.name} - outside date range "
                f"(created: {log_file.created})"
            )
            stats.skipped_files += 1
            return

        # Extract event data from log file
        event_data = extract_event_from_log(log_file)
        if not event_data:
            log.warning(f"Failed to extract event data from {log_file.name}, skipping")
            stats.skipped_files += 1
            return

        stats.files_processed += 1

        # Create and capture events
        self._create_and_capture_submission_event(event_data, stats)
        self._create_and_capture_pass_qc_event(event_data, stats)

    def _create_and_capture_submission_event(
        self, event_data, stats: ProcessingStatistics
    ) -> None:
        """Create and capture a submission event.

        Args:
            event_data: The extracted event data
            stats: Statistics object to update
        """
        submission_event = self._event_generator.create_submission_event(event_data)
        if not submission_event:
            return

        if self._dry_run:
            log.info(
                f"[DRY RUN] Would create submission event: "
                f"{submission_event.action} for {submission_event.ptid} "
                f"at {submission_event.timestamp}"
            )
        elif self._event_capture:
            self._event_capture.capture_event(submission_event)
            log.debug(f"Captured submission event for {submission_event.ptid}")

        stats.submission_events_created += 1

    def _create_and_capture_pass_qc_event(
        self, event_data, stats: ProcessingStatistics
    ) -> None:
        """Create and capture a pass-qc event if applicable.

        Args:
            event_data: The extracted event data
            stats: Statistics object to update
        """
        pass_qc_event = self._event_generator.create_pass_qc_event(event_data)
        if not pass_qc_event:
            return

        if self._dry_run:
            log.info(
                f"[DRY RUN] Would create pass-qc event: "
                f"{pass_qc_event.action} for {pass_qc_event.ptid} "
                f"at {pass_qc_event.timestamp}"
            )
        elif self._event_capture:
            self._event_capture.capture_event(pass_qc_event)
            log.debug(f"Captured pass-qc event for {pass_qc_event.ptid}")

        stats.pass_qc_events_created += 1

    def _log_summary(self, stats: ProcessingStatistics) -> None:
        """Log summary statistics.

        Args:
            stats: Statistics to log
        """
        log.info(
            f"Processing complete: {stats.files_processed} files processed, "
            f"{stats.submission_events_created} submission events, "
            f"{stats.pass_qc_events_created} pass-qc events, "
            f"{stats.skipped_files} files skipped, "
            f"{stats.errors_encountered} errors"
        )

    def _discover_log_files(self) -> list[FileEntry]:
        """Discover all QC status log files in the project.

        Returns:
            List of FileEntry objects for QC status log files
        """
        # QC status log files follow the pattern: *_qc-status.log
        # They are stored at the project level
        log_files = [
            file for file in self._project.files if file.name.endswith("_qc-status.log")
        ]

        return log_files
