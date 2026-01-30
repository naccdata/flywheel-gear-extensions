"""Event processors for the Transactional Event Scraper.

This module provides two specialized processors that work together to
discover, extract, match, and capture transactional events:

1. SubmitEventProcessor: Processes QC status log files to create submit
   events. These events are initially stored in an UnmatchedSubmitEvents
   collection awaiting enrichment with packet information.

2. QCEventProcessor: Processes form JSON files to create QC events and
   match them with previously created submit events. When a match is found,
   the submit event is enriched with packet and visit number information
   from the JSON file, then both events are captured to S3.

The two-phase processing approach ensures that:
- Submit events are created from QC logs (which contain submission timestamps)
- QC events are created from JSON files (which contain packet information)
- Events are matched on ptid, date, and module (fields guaranteed to be in
  both sources)
- Submit events are enriched with packet information before capture
- Only PASS QC events are captured to the event bucket

This design enables complete event records with both submission timestamps
and packet information, which are stored in different source files.
"""

import logging
from typing import List, Optional

from error_logging.error_logger import ErrorLogTemplate
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import (
    FileQCModel,
)

from event_capture.event_capture import VisitEventCapture
from event_capture.event_generator import EventGenerator
from event_capture.log_file_processor import extract_event_from_log
from event_capture.models import (
    DateRange,
    EventMatchKey,
    QCEventData,
    UnmatchedSubmitEvents,
)
from event_capture.visit_events import VisitEvent
from event_capture.visit_extractor import VisitMetadataExtractor

log = logging.getLogger(__name__)


class SubmitEventProcessor:
    """Processes QC status logs to create submit events.

    This processor is responsible for Phase 1 of the event scraping workflow:
    discovering QC status log files and extracting submit events from them.
    Submit events are created with submission timestamps from the log file
    creation time, but initially lack packet information (which is only
    available in JSON files).

    The processor stores all created submit events in an UnmatchedSubmitEvents
    collection, where they await enrichment during Phase 2 when JSON files
    are processed.

    Attributes:
        _project: Project adaptor for accessing Flywheel project files
        _event_generator: Generator for creating VisitEvent objects
        _unmatched_events: Collection for storing submit events awaiting enrichment
        _date_filter: Optional date range for filtering files by creation time
    """

    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        date_filter: Optional[DateRange] = None,
    ):
        """Initialize the SubmitEventProcessor.

        Args:
            project: Project adaptor for accessing Flywheel project files
            event_generator: Generator for creating VisitEvent objects
            unmatched_events: Collection for storing submit events awaiting enrichment
            date_filter: Optional date range for filtering files by creation time
        """
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._date_filter = date_filter

    def process_qc_logs(self) -> None:
        """Discover and process all QC status logs.

        This method discovers all QC status log files in the project and
        processes each one to create submit events. Events are added to
        the unmatched events collection for later enrichment.

        Errors during individual file processing are logged but do not
        stop the overall processing.
        """
        log_files = self._discover_qc_logs()
        log.info(f"Discovered {len(log_files)} QC status log files")

        for log_file in log_files:
            try:
                self._process_log_file(log_file)
            except Exception as error:
                log.error(f"Error processing {log_file.name}: {error}", exc_info=True)

    def _process_log_file(self, log_file: FileEntry) -> None:
        """Process a single QC status log file.

        Extracts event data from the log file, creates a submit event,
        and adds it to the unmatched events collection.

        Args:
            log_file: The QC status log file to process
        """
        # Apply date filter
        if self._date_filter and not self._date_filter.includes_file(log_file.created):
            log.debug(f"Skipping {log_file.name} - outside date range")
            return

        # Extract event data from log
        event_data = extract_event_from_log(log_file)
        if not event_data:
            log.warning(f"Failed to extract event data from {log_file.name}")
            return

        # Create submit event
        submit_event = self._event_generator.create_submission_event(event_data)
        if not submit_event:
            log.warning(f"Failed to create submit event from {log_file.name}")
            return

        # Add to unmatched collection
        self._unmatched_events.add(submit_event)
        log.debug(
            f"Created submit event for {submit_event.ptid} "
            f"{submit_event.visit_date} {submit_event.module}"
        )

    def _discover_qc_logs(self) -> List[FileEntry]:
        """Discover all QC status log files in the project.

        Returns:
            List of QC status log file entries
        """
        return self._project.get_matching_files(
            "parent_ref.type=project,name=~.+qc-status.log"
        )


class QCEventProcessor:
    """Processes JSON files to create and match QC events.

    This processor is responsible for Phase 2 of the event scraping workflow:
    discovering form JSON files, extracting QC event data, and matching QC
    events with previously created submit events.

    When a match is found:
    1. The submit event is enriched with packet and visit number from the JSON
    2. The enriched submit event is captured to S3
    3. If QC status is PASS, the QC event is also captured to S3

    When no match is found, a warning is logged indicating potential data loss.

    The matching process uses EventMatchKey (ptid, date, module) to correlate
    events. Module matching is case-insensitive.

    Attributes:
        _project: Project adaptor for accessing Flywheel project files
        _event_generator: Generator for creating VisitEvent objects
        _unmatched_events: Collection of submit events awaiting enrichment
        _event_capture: Event capture for storing events to S3
        _dry_run: Whether to perform a dry run without capturing events
        _date_filter: Optional date range for filtering files by creation time
        _error_log_template: Template for generating QC log filenames
    """

    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        event_capture: Optional[VisitEventCapture],
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None,
    ):
        """Initialize the QCEventProcessor.

        Args:
            project: Project adaptor for accessing Flywheel project files
            event_generator: Generator for creating VisitEvent objects
            unmatched_events: Collection of submit events awaiting enrichment
            event_capture: Event capture for storing events to S3 (None for dry-run)
            dry_run: Whether to perform a dry run without capturing events
            date_filter: Optional date range for filtering files by creation time
        """
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._event_capture = event_capture
        self._dry_run = dry_run
        self._date_filter = date_filter
        self._error_log_template = ErrorLogTemplate()

    def process_json_files(self) -> None:
        """Discover and process all JSON files.

        This method discovers all form JSON files in the project and
        processes each one to create QC events and match them with
        submit events.

        Errors during individual file processing are logged but do not
        stop the overall processing.
        """
        json_files = self._discover_json_files()
        log.info(f"Discovered {len(json_files)} JSON files")

        for json_file in json_files:
            try:
                self._process_json_file(json_file)
            except Exception as error:
                log.error(f"Error processing {json_file.name}: {error}", exc_info=True)

    def _process_json_file(self, json_file: FileEntry) -> None:
        """Process a single JSON file.

        Extracts QC event data, creates a match key, attempts to find
        a matching submit event, and either enriches and captures the
        matched events or logs a warning about the unmatched QC event.

        Args:
            json_file: The form JSON file to process
        """
        # Apply date filter
        if self._date_filter and not self._date_filter.includes_file(json_file.created):
            log.debug(f"Skipping {json_file.name} - outside date range")
            return

        # Extract QC event data
        qc_event_data = self._extract_qc_event_data(json_file)
        if not qc_event_data:
            log.debug(f"No QC event data for {json_file.name}")
            return

        # MATCHING LOGIC:
        # Create a match key from the QC event data using ptid, date, and module.
        # These are the only fields guaranteed to be in both the QC status log
        # filename and the JSON file metadata, making them reliable for matching.
        # Module is automatically normalized to uppercase for case-insensitive
        # matching (e.g., "UDS" matches "uds").
        match_key = EventMatchKey.from_visit_metadata(qc_event_data.visit_metadata)

        # Try to find a matching submit event in the unmatched collection.
        # find_and_remove() performs O(1) lookup using the match key as a dict key,
        # and removes the event from the collection to prevent duplicate matches.
        # Returns None if no matching submit event exists.
        submit_event = self._unmatched_events.find_and_remove(match_key)

        if submit_event:
            # Match found: We have both a submit event (from QC log) and QC event
            # data (from JSON file). Now we can create complete event records.

            # Enrich the submit event with packet and visit number from the JSON
            # file, then capture it to S3. This gives us a complete submit event
            # with both submission timestamp (from QC log) and packet info (from JSON).
            self._enrich_and_push_submit_event(submit_event, qc_event_data)

            # If QC status is PASS, also create and capture a separate QC event.
            # Non-PASS statuses (FAIL, ERROR, etc.) don't get QC events captured.
            if qc_event_data.qc_status == "PASS":
                self._push_qc_event(qc_event_data)
        else:
            # No match found: This QC event has no corresponding submit event.
            # This can happen if:
            # 1. The QC log file is missing or wasn't processed
            # 2. The QC log filename doesn't match the expected pattern
            # 3. The JSON file was created before we started tracking submit events
            # Log a warning since this represents potential data loss.
            log.warning(
                f"Unmatched QC event (no corresponding submit event): "
                f"ptid={match_key.ptid}, date={match_key.date}, "
                f"module={match_key.module}, status={qc_event_data.qc_status}"
            )

    def _extract_qc_event_data(self, json_file: FileEntry) -> Optional[QCEventData]:
        """Extract QC event data from JSON file.

        Extracts visit metadata from the JSON file's custom info and
        finds the corresponding QC status log to get the QC status.

        Args:
            json_file: The form JSON file to extract data from

        Returns:
            QCEventData if extraction successful, None otherwise
        """
        # Extract visit metadata from JSON file (includes packet)
        # Note: VisitMetadataExtractor is imported from event_capture.visit_extractor
        visit_metadata = VisitMetadataExtractor.from_json_file_metadata(json_file)
        if not visit_metadata:
            return None

        if not VisitMetadataExtractor.is_valid_for_event(visit_metadata):
            return None

        # Find corresponding QC status log
        qc_log_file = self._find_qc_status_for_json_file(json_file)
        if not qc_log_file:
            log.debug(f"No QC status log found for {json_file.name}")
            return None

        # Extract QC status
        qc_model = FileQCModel.create(qc_log_file)
        qc_status = qc_model.get_file_status()

        return QCEventData(
            visit_metadata=visit_metadata,
            qc_status=qc_status,
            qc_completion_timestamp=qc_log_file.modified,
        )

    def _find_qc_status_for_json_file(
        self, json_file: FileEntry
    ) -> Optional[FileEntry]:
        """Find QC status log for JSON file using ErrorLogTemplate.

        Uses the ErrorLogTemplate to generate the expected QC log filename
        based on the JSON file's metadata, then looks up that file in the
        project.

        Args:
            json_file: The form JSON file to find QC log for

        Returns:
            QC status log file entry if found, None otherwise
        """
        if not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        module = forms_json.get("module")
        if not module:
            return None

        # Generate expected QC log filename
        qc_log_name = self._error_log_template.instantiate(
            record=forms_json, module=module
        )
        if not qc_log_name:
            return None

        # Look up in project files
        try:
            return self._project.get_file(qc_log_name)
        except Exception:
            return None

    def _enrich_and_push_submit_event(
        self, submit_event: VisitEvent, qc_event_data: QCEventData
    ) -> None:
        """Enrich submit event with QC data and push to bucket.

        Enriches the submit event by filling in None values with data
        from the QC event (packet and visit number). Then captures the
        enriched event to S3.

        Args:
            submit_event: The submit event to enrich and capture
            qc_event_data: The QC event data to use for enrichment
        """
        # ENRICHMENT LOGIC:
        # Fill in missing fields in the submit event with data from the QC event.
        # This is a "fill-in-the-blanks" operation - we only replace None values,
        # never overwriting existing data. This preserves the submit event as the
        # "source of truth" while adding information that was only available in
        # the JSON file.

        # Packet information is only available in JSON files (not in QC logs),
        # so submit events always have packet=None initially. Fill it in from
        # the JSON file metadata.
        if submit_event.packet is None:
            submit_event.packet = qc_event_data.visit_metadata.packet

        # Visit number might be missing from the QC log but present in the JSON.
        # Only fill it in if the submit event doesn't already have it.
        if submit_event.visit_number is None:
            submit_event.visit_number = qc_event_data.visit_metadata.visitnum

        # Capture the enriched submit event to S3.
        # The event now has complete information: submission timestamp from the
        # QC log and packet/visit number from the JSON file.
        if self._dry_run:
            log.info(
                f"[DRY RUN] Would push enriched submit event: "
                f"{submit_event.ptid} {submit_event.visit_date} "
                f"{submit_event.module} (packet={submit_event.packet})"
            )
        elif self._event_capture:
            self._event_capture.capture_event(submit_event)
            log.info(
                f"Pushed enriched submit event: {submit_event.ptid} "
                f"{submit_event.visit_date} {submit_event.module}"
            )

    def _push_qc_event(self, qc_event_data: QCEventData) -> None:
        """Create and push QC pass event.

        Creates a QC event from the QC event data and captures it to S3.
        Only called for PASS QC events.

        Args:
            qc_event_data: The QC event data to create event from
        """
        qc_event = self._event_generator.create_qc_event(qc_event_data)
        if not qc_event:
            log.warning("Failed to create QC event")
            return

        if self._dry_run:
            log.info(
                f"[DRY RUN] Would push QC pass event: "
                f"{qc_event.ptid} {qc_event.visit_date} {qc_event.module}"
            )
        elif self._event_capture:
            self._event_capture.capture_event(qc_event)
            log.debug(
                f"Pushed QC pass event: {qc_event.ptid} "
                f"{qc_event.visit_date} {qc_event.module}"
            )

    def _discover_json_files(self) -> List[FileEntry]:
        """Discover all JSON files in project acquisitions.

        Returns:
            List of form JSON file entries
        """

        return self._project.get_matching_files(
            "parent_ref.type=acquisition,modality=Form,name=~.+json"
        )
