"""EventScraper orchestrator for discovering and processing QC status log files
and form JSON files."""

import logging
from typing import Optional

from event_capture.event_capture import VisitEventCapture
from event_capture.event_generator import EventGenerator
from event_capture.event_processor import QCEventProcessor, SubmitEventProcessor
from event_capture.models import DateRange, UnmatchedSubmitEvents
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor

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

        # Shared components
        self._event_generator = EventGenerator(project)
        self._unmatched_events = UnmatchedSubmitEvents()

        # Processors
        self._submit_processor = SubmitEventProcessor(
            project=project,
            event_generator=self._event_generator,
            unmatched_events=self._unmatched_events,
            date_filter=date_filter,
        )

        self._qc_processor = QCEventProcessor(
            project=project,
            event_generator=self._event_generator,
            unmatched_events=self._unmatched_events,
            event_capture=event_capture,
            dry_run=dry_run,
            date_filter=date_filter,
        )

    def scrape_events(self) -> None:
        """Execute the scraping process in three phases.

        Phase 1: Process QC logs to create submit events Phase 2:
        Process JSON files to create and match QC events Phase 3: Report
        unmatched submit events
        """
        log.info("Starting event scraping")

        # Phase 1: Process QC logs to create submit events
        log.info("Phase 1: Processing QC status logs")
        self._submit_processor.process_qc_logs()
        log.info(
            f"Created {self._unmatched_events.count()} submit events "
            f"awaiting enrichment"
        )

        # Phase 2: Process JSON files to create and match QC events
        log.info("Phase 2: Processing JSON files and matching events")
        self._qc_processor.process_json_files()

        # Phase 3: Report unmatched submit events
        remaining = self._unmatched_events.get_remaining()
        if remaining:
            log.warning(
                f"Processing complete with {len(remaining)} unmatched submit "
                f"events (no corresponding JSON/QC data found)"
            )
            # Log sample of unmatched events for investigation
            for event in remaining[:5]:  # Log first 5
                log.warning(
                    f"  Unmatched: ptid={event.ptid}, date={event.visit_date}, "
                    f"module={event.module}"
                )
            if len(remaining) > 5:
                log.warning(f"  ... and {len(remaining) - 5} more")
        else:
            log.info("Processing complete: all submit events matched and enriched")
