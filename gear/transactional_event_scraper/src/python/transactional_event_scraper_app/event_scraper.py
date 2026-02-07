"""EventScraper orchestrator for the Transactional Event Scraper.

This module provides the main orchestrator that coordinates the three-phase
event scraping workflow:

Phase 1: Process QC status logs to create submit events
    - Discovers QC status log files at the project level
    - Extracts submission events with timestamps
    - Stores events in UnmatchedSubmitEvents collection

Phase 2: Process JSON files to create and match QC events
    - Discovers form JSON files in acquisitions
    - Extracts QC event data including packet information
    - Matches QC events with submit events using EventMatchKey
    - Enriches matched submit events with packet information
    - Captures enriched submit events and PASS QC events to S3

Phase 3: Report unmatched submit events
    - Logs warnings for any submit events that couldn't be matched
    - Indicates potential data loss or missing JSON files

The EventScraper uses dependency injection to coordinate two specialized
processors (SubmitEventProcessor and QCEventProcessor) and a shared
UnmatchedSubmitEvents collection for efficient event matching.
"""

import logging
from typing import Optional

from event_capture.event_capture import VisitEventCapture
from event_capture.event_generator import EventGenerator
from event_capture.event_processor import QCEventProcessor, SubmitEventProcessor
from event_capture.models import DateRange, UnmatchedSubmitEvents
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor

log = logging.getLogger(__name__)


class EventScraper:
    """Main orchestrator that coordinates the three-phase event scraping
    workflow.

    The EventScraper is responsible for orchestrating the complete event
    scraping process, which involves:

    1. Creating and coordinating two specialized processors:
       - SubmitEventProcessor: Processes QC status logs
       - QCEventProcessor: Processes JSON files and matches events

    2. Managing shared state through UnmatchedSubmitEvents collection

    3. Executing the three-phase workflow:
       - Phase 1: Process QC logs to create submit events
       - Phase 2: Process JSON files to match and enrich events
       - Phase 3: Report any unmatched submit events

    The orchestrator uses dependency injection to provide shared components
    (EventGenerator, UnmatchedSubmitEvents) to both processors, ensuring
    they work with the same data and can coordinate event matching.

    Attributes:
        _project: Project adaptor for accessing Flywheel project files
        _event_capture: Event capture for storing events to S3
        _dry_run: Whether to perform a dry run without capturing events
        _date_filter: Optional date range for filtering files
        _event_generator: Shared generator for creating VisitEvent objects
        _unmatched_events: Shared collection for event matching
        _submit_processor: Processor for QC status logs
        _qc_processor: Processor for JSON files
    """

    def __init__(
        self,
        project: ProjectAdaptor,
        event_capture: Optional[VisitEventCapture] = None,
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None,
    ) -> None:
        """Initialize the EventScraper.

        Creates the shared components (EventGenerator, UnmatchedSubmitEvents)
        and initializes both processors with these shared components.

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
        """Execute the three-phase event scraping workflow.

        Phase 1: Process QC logs to create submit events
            - Discovers and processes all QC status log files
            - Creates submit events and stores them in unmatched collection
            - Logs count of submit events awaiting enrichment

        Phase 2: Process JSON files to match and enrich events
            - Discovers and processes all form JSON files
            - Matches QC events with submit events
            - Enriches and captures matched events
            - Logs warnings for unmatched QC events

        Phase 3: Report unmatched submit events
            - Logs warning if any submit events remain unmatched
            - Provides sample of unmatched events for investigation
            - Indicates potential data loss or missing JSON files

        The workflow is designed to be resilient to individual file
        processing failures - errors are logged but don't stop the
        overall process.
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
