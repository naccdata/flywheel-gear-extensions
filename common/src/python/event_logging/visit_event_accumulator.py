"""Visit event accumulator for tracking events throughout pipeline
processing."""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from configs.ingest_configs import ModuleConfigs
from dates.dates import datetime_from_form_date
from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent
from flywheel import Project
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from nacc_common.error_models import VisitKeys
from nacc_common.field_names import FieldNames
from pydantic import BaseModel

log = logging.getLogger(__name__)


class PendingVisitData(BaseModel):
    """Holds partial visit data until complete."""

    visit_number: str  # Visit number (e.g., "01", "02")
    session_id: str  # Session container ID
    acquisition_id: str  # Acquisition container ID (module level)
    module: str
    project_label: str
    center_label: str
    pipeline_adcid: int

    # Timestamps for different event types
    upload_timestamp: datetime  # For "submit" event
    completion_timestamp: Optional[datetime] = None  # For outcome event

    # Original CSV filename (for logging/debugging)
    csv_filename: str = ""

    model_config = {"arbitrary_types_allowed": True}


class VisitEventAccumulator:
    """Accumulates visit event data throughout pipeline processing.

    Collects metadata at various stages and creates complete VisitEvents
    once all required information is available.

    Uses visit_number as the key since it uniquely identifies a visit.
    Visit number is extracted from session label using module config template.
    """

    def __init__(
        self,
        event_logger: VisitEventLogger,
        module_configs: Dict[str, ModuleConfigs],
        proxy: FlywheelProxy,
    ):
        """Initialize the accumulator.

        Args:
            event_logger: Logger for writing events
            module_configs: Dictionary of module configurations keyed by module name
            proxy: Flywheel proxy for querying containers
        """
        self.__event_logger = event_logger
        self.__module_configs = module_configs
        self.__proxy = proxy

        # Key: visit_number, Value: PendingVisitData
        self.__pending: Dict[str, PendingVisitData] = {}

    @property
    def pending(self) -> Dict[str, PendingVisitData]:
        """Get pending visit data (for testing).

        Returns:
            Dictionary of pending visit data keyed by visit_number
        """
        return self.__pending

    def __extract_visit_number_from_session(
        self, session_label: str, module: str
    ) -> Optional[str]:
        """Extract visit number from session label using module config
        template.

        The session label follows the template pattern from hierarchy_labels.
        For example, template "FORMS-VISIT-${visitnum}" with label "FORMS-VISIT-01"
        should extract "01".

        Note: Not all modules have visit numbers in their session labels.
        For modules without visit numbers, this will return None and event
        logging will be skipped.

        Args:
            session_label: Session label (e.g., "FORMS-VISIT-01")
            module: Module name to get config

        Returns:
            Visit number if extracted, None otherwise
        """
        module_config = self.__module_configs.get(module.upper())
        if not module_config:
            log.warning(f"No module config found for {module}")
            return None

        # Get session template from hierarchy_labels
        hierarchy = module_config.hierarchy_labels
        if not hierarchy or not hierarchy.session:
            log.warning(f"No session hierarchy config for {module}")
            return None

        session_config = hierarchy.session
        template = session_config.template

        # Convert template to regex pattern
        # Replace ${visitnum} with capture group
        pattern = template.replace("${visitnum}", r"(\d+)")
        # Escape other special regex characters
        pattern = pattern.replace("-", r"\-")

        # Apply transform if specified
        transform = session_config.transform
        if transform == "upper":
            session_label = session_label.upper()
        elif transform == "lower":
            session_label = session_label.lower()

        # Extract visit number
        match = re.match(pattern, session_label)
        if match:
            return match.group(1)

        log.warning(
            f"Could not extract visit number from session label '{session_label}' "
            f"using pattern '{pattern}'"
        )
        return None

    def record_file_queued(
        self, *, file: FileEntry, module: str, project: Project
    ) -> None:
        """Record when a file is queued for processing.

        Captures the upload timestamp and project metadata.

        Args:
            file: The CSV file being queued
            module: Module name (e.g., "UDS")
            project: Project container
        """
        # Get acquisition (module level) and session (visit level)
        acquisition_id = file.parent_ref.id
        acquisition = self.__proxy.get_container_by_id(acquisition_id)
        session_id = acquisition.parents.session
        session = self.__proxy.get_container_by_id(session_id)

        # Extract visit number from session label
        visit_number = self.__extract_visit_number_from_session(session.label, module)
        if not visit_number:
            log.warning(
                f"Could not extract visit number from session {session.label}, "
                f"cannot track events for {file.name}"
            )
            return

        # Get pipeline_adcid from project metadata
        pipeline_adcid = project.info.get("pipeline_adcid")
        if pipeline_adcid is None:
            log.warning(
                f"No pipeline_adcid in project {project.label}, "
                f"cannot track events for {file.name}"
            )
            return

        # Use file creation timestamp as upload time
        upload_timestamp = file.created

        # Key by visit_number
        self.__pending[visit_number] = PendingVisitData(
            visit_number=visit_number,
            session_id=session_id,
            acquisition_id=acquisition_id,
            module=module.upper(),
            project_label=project.label,
            center_label=project.group,
            pipeline_adcid=pipeline_adcid,
            upload_timestamp=upload_timestamp,
            csv_filename=file.name,
        )

        log.debug(f"Recorded queued file {file.name} for visit {visit_number}")

    def finalize_and_log_events(
        self, *, file: FileEntry, module: str, pipeline_succeeded: bool
    ) -> None:
        """Finalize accumulated data and emit all applicable events.

        Called after pipeline completes. Retrieves JSON metadata and creates
        events based on whether pending data exists:
        
        - If pending data exists (Phase 1 was called):
          Logs "submit" event + outcome event ("pass-qc" or "not-pass-qc")
        - If no pending data (re-evaluation scenario):
          Logs only outcome event ("pass-qc" or "not-pass-qc")
          
        Re-evaluation scenarios include:
        - QC alerts approved after initial failure
        - Dependency resolution (e.g., UDS packet cleared, unblocking follow-up visits)

        Args:
            file: The original CSV file (for getting acquisition/session)
            module: Module name
            pipeline_succeeded: Whether the pipeline completed successfully
        """
        # Get session and extract visit number
        acquisition_id = file.parent_ref.id
        acquisition = self.__proxy.get_container_by_id(acquisition_id)
        session_id = acquisition.parents.session
        session = self.__proxy.get_container_by_id(session_id)

        visit_number = self.__extract_visit_number_from_session(session.label, module)
        if not visit_number:
            log.warning(
                f"Could not extract visit number from session {session.label}, "
                f"cannot log events for {file.name}"
            )
            return

        # Check if we have pending data for this visit
        # Note: Pending data only exists if record_file_queued() was called (Phase 1)
        # For re-evaluations (e.g., after UDS packet cleared), there is no pending data
        pending = self.__pending.get(visit_number)
        if not pending:
            log.info(
                f"No pending data for visit {visit_number}. "
                f"This is a re-evaluation (not a new submission). "
                f"Will log outcome event only, no submit event."
            )
            # Continue processing to log outcome event
            # We'll need to get metadata differently without pending data
            # For now, return since we need upload_timestamp from pending data
            # TODO: Support re-evaluation scenario by extracting metadata from JSON only
            return

        # Record completion timestamp
        pending.completion_timestamp = datetime.now()

        try:
            # Find JSON file in acquisition (module level)
            # IMPORTANT: JSON file MUST exist for "pass-qc" events
            # - JSON presence indicates form-transformer succeeded
            # - JSON absence means early failure (identifier-lookup or form-transformer)
            # - Without JSON, we cannot extract visit metadata needed for events
            json_file = self.__find_json_file(acquisition, module)

            if not json_file:
                log.warning(
                    f"No JSON file found in acquisition {acquisition_id}. "
                    f"Pipeline failed at identifier-lookup or form-transformer. "
                    f"Cannot log events without visit metadata from JSON file."
                )
                return

            # Extract visit metadata from JSON
            visit_metadata = self.__extract_visit_metadata(json_file, module)
            if not visit_metadata:
                log.warning(f"Could not extract visit metadata from {json_file.name}")
                return

            # Create and log "submit" event (always logged)
            submit_event = VisitEvent(
                action="submit",
                pipeline_adcid=pending.pipeline_adcid,
                project_label=pending.project_label,
                center_label=pending.center_label,
                gear_name="form-scheduler",
                ptid=visit_metadata["ptid"],
                visit_date=visit_metadata["visit_date"],
                visit_number=visit_metadata["visit_number"],
                datatype="form",
                module=pending.module,
                packet=visit_metadata.get("packet"),
                timestamp=pending.upload_timestamp,
            )
            self.__event_logger.log_event(submit_event)
            log.info(
                f"Logged submit event for {visit_metadata['ptid']} "
                f"visit {visit_metadata['visit_number']}"
            )

            # Create and log outcome event (pass-qc or not-pass-qc)
            outcome_action = "pass-qc" if pipeline_succeeded else "not-pass-qc"
            outcome_event = VisitEvent(
                action=outcome_action,
                pipeline_adcid=pending.pipeline_adcid,
                project_label=pending.project_label,
                center_label=pending.center_label,
                gear_name="form-scheduler",
                ptid=visit_metadata["ptid"],
                visit_date=visit_metadata["visit_date"],
                visit_number=visit_metadata["visit_number"],
                datatype="form",
                module=pending.module,
                packet=visit_metadata.get("packet"),
                timestamp=pending.completion_timestamp,
            )
            self.__event_logger.log_event(outcome_event)
            log.info(
                f"Logged {outcome_action} event for {visit_metadata['ptid']} "
                f"visit {visit_metadata['visit_number']}"
            )

        except Exception as error:
            log.error(
                f"Error logging events for visit {visit_number}: {error}",
                exc_info=True,
            )
        finally:
            # Clean up pending data
            del self.__pending[visit_number]

    def __find_json_file(self, acquisition: Any, module: str) -> Optional[FileEntry]:
        """Find the JSON file in the acquisition.

        Args:
            acquisition: Acquisition container
            module: Module name

        Returns:
            JSON FileEntry if found, None otherwise
        """
        # Look for .json files
        json_files = [f for f in acquisition.files if f.name.endswith(".json")]

        if not json_files:
            return None

        # If multiple JSON files, try to match by module name
        if len(json_files) > 1:
            module_lower = module.lower()
            matching = [f for f in json_files if module_lower in f.name.lower()]
            if matching:
                return matching[0]

        # Return first/only JSON file
        return json_files[0]

    def __extract_visit_metadata(
        self, json_file: FileEntry, module: str
    ) -> Optional[Dict[str, Any]]:
        """Extract visit metadata from JSON file.

        Uses existing infrastructure from nacc_common for parsing form metadata.

        Args:
            json_file: JSON FileEntry with form metadata
            module: Module name

        Returns:
            Dict with ptid, visit_date, visit_number, packet if successful
        """
        # Get form metadata from file.info.forms.json
        form_metadata = json_file.info.get("forms", {}).get("json", {})
        if not form_metadata:
            log.warning(f"No form metadata in {json_file.name}")
            return None

        # Get module config to know field names
        module_config = self.__module_configs.get(module.upper())
        if not module_config:
            log.warning(f"No module config found for {module}")
            return None

        # Use VisitKeys.create_from() to extract visit information
        # This is the standard way to extract visit data from form records
        date_field = module_config.date_field
        visit_keys = VisitKeys.create_from(form_metadata, date_field)

        # Validate required fields
        if not all([visit_keys.ptid, visit_keys.date, visit_keys.visitnum]):
            log.warning(
                f"Missing required fields in {json_file.name}: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"visitnum={visit_keys.visitnum}"
            )
            return None

        # Parse visit date using common date utility
        if not visit_keys.date:
            log.warning(f"Missing date in {json_file.name}")
            return None

        try:
            visit_datetime = datetime_from_form_date(visit_keys.date)
            visit_date = visit_datetime.date()
        except ValueError as error:
            log.warning(f"Could not parse date {visit_keys.date}: {error}")
            return None

        # Get packet from form metadata (not in VisitKeys.create_from)
        packet = form_metadata.get(FieldNames.PACKET)

        return {
            "ptid": visit_keys.ptid,
            "visit_date": visit_date,
            "visit_number": visit_keys.visitnum,
            "packet": str(packet) if packet else None,
        }
