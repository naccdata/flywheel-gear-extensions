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
    """Processes QC status logs to create submit events."""

    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        date_filter: Optional[DateRange] = None,
    ):
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._date_filter = date_filter

    def process_qc_logs(self) -> None:
        """Discover and process all QC status logs."""
        log_files = self._discover_qc_logs()
        log.info(f"Discovered {len(log_files)} QC status log files")

        for log_file in log_files:
            try:
                self._process_log_file(log_file)
            except Exception as error:
                log.error(f"Error processing {log_file.name}: {error}", exc_info=True)

    def _process_log_file(self, log_file: FileEntry) -> None:
        """Process a single QC status log file."""
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
        """Discover all QC status log files in the project."""
        return self._project.get_matching_files(
            "parent_ref.type=project,name=~.+qc-status.log"
        )


class QCEventProcessor:
    """Processes JSON files to create and match QC events."""

    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        event_capture: Optional[VisitEventCapture],
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None,
    ):
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._event_capture = event_capture
        self._dry_run = dry_run
        self._date_filter = date_filter
        self._error_log_template = ErrorLogTemplate()

    def process_json_files(self) -> None:
        """Discover and process all JSON files."""
        json_files = self._discover_json_files()
        log.info(f"Discovered {len(json_files)} JSON files")

        for json_file in json_files:
            try:
                self._process_json_file(json_file)
            except Exception as error:
                log.error(f"Error processing {json_file.name}: {error}", exc_info=True)

    def _process_json_file(self, json_file: FileEntry) -> None:
        """Process a single JSON file."""
        # Apply date filter
        if self._date_filter and not self._date_filter.includes_file(json_file.created):
            log.debug(f"Skipping {json_file.name} - outside date range")
            return

        # Extract QC event data
        qc_event_data = self._extract_qc_event_data(json_file)
        if not qc_event_data:
            log.debug(f"No QC event data for {json_file.name}")
            return

        # Create match key
        match_key = EventMatchKey.from_visit_metadata(qc_event_data.visit_metadata)

        # Try to find matching submit event
        submit_event = self._unmatched_events.find_and_remove(match_key)

        if submit_event:
            # Match found - enrich and push submit event
            self._enrich_and_push_submit_event(submit_event, qc_event_data)

            # If QC passed, also push QC event
            if qc_event_data.qc_status == "PASS":
                self._push_qc_event(qc_event_data)
        else:
            # No match - log warning
            log.warning(
                f"Unmatched QC event (no corresponding submit event): "
                f"ptid={match_key.ptid}, date={match_key.date}, "
                f"module={match_key.module}, status={qc_event_data.qc_status}"
            )

    def _extract_qc_event_data(self, json_file: FileEntry) -> Optional[QCEventData]:
        """Extract QC event data from JSON file."""
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
        """Find QC status log for JSON file using ErrorLogTemplate."""
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
        """Enrich submit event with QC data and push to bucket."""
        # Enrich: replace None values with QC event data
        if submit_event.packet is None:
            submit_event.packet = qc_event_data.visit_metadata.packet

        if submit_event.visit_number is None:
            submit_event.visit_number = qc_event_data.visit_metadata.visitnum

        # Push enriched submit event
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
        """Create and push QC pass event."""
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
        """Discover all JSON files in project acquisitions."""

        return self._project.get_matching_files(
            "parent_ref.type=acquisition,modality=Form,name=~.+json"
        )
