"""Visit event accumulator for tracking events throughout pipeline
processing."""

import logging
from datetime import datetime
from typing import Any, Dict, NamedTuple, Optional

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


class VisitKey(NamedTuple):
    """Composite key for uniquely identifying a visit.

    Aligns with QC log file naming pattern: {ptid}_{visitdate}_{module}_qc-status.log

    Note: There is only one visit per year per participant at a center (ADCID).
    However, each visit can have multiple modules (UDS, FTLD, LBD, etc.).
    """

    ptid: str  # Participant ID
    visit_date: str  # Visit date in YYYY-MM-DD format
    module: str  # Module name (e.g., "UDS", "FTLD", "LBD")


class PendingVisitData(BaseModel):
    """Holds partial visit data until complete."""

    ptid: str  # Participant ID
    visit_date: str  # Visit date (YYYY-MM-DD format)
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

    # Track whether submit event was already logged
    submit_logged: bool = False

    # Original CSV filename (for logging/debugging)
    csv_filename: str = ""

    model_config = {"arbitrary_types_allowed": True}


class VisitEventAccumulator:
    """Accumulates visit event data throughout pipeline processing.

    Collects metadata at various stages and creates complete VisitEvents
    once all required information is available.

    Uses (ptid, visit_date, module) as the composite key to uniquely identify
    a visit. This aligns with the QC log file naming pattern:
    {ptid}_{visitdate}_{module}_qc-status.log

    Note: There is only one visit per year per participant at a center (ADCID).
    However, each visit can have multiple modules (UDS, FTLD, LBD, etc.),
    so module is included in the key.
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

        # Key: VisitKey, Value: PendingVisitData
        self.__pending: Dict[VisitKey, PendingVisitData] = {}

    @property
    def pending(self) -> Dict[VisitKey, PendingVisitData]:
        """Get pending visit data (for testing).

        Returns:
            Dictionary of pending visit data keyed by VisitKey
        """
        return self.__pending

    def record_file_queued(
        self, *, file: FileEntry, module: str, project: Project
    ) -> None:
        """Record when a file is queued and immediately log submit event.

        Uses QC log file at PROJECT level to extract visit metadata.
        Logs "submit" event immediately if QC log is available.

        Args:
            file: The CSV file being queued (at PROJECT level)
            module: Module name (e.g., "UDS")
            project: Project container
        """
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

        # Look for QC log file at PROJECT level
        # Pattern: {ptid}_{visitdate}_{module}_qc-status.log
        qc_log_file = self.__find_qc_log_file(project, module)

        if not qc_log_file:
            log.info(
                f"No QC log file found for {file.name} yet. "
                f"Will log submit event after identifier-lookup creates QC log."
            )
            # Cannot log submit event without metadata from QC log
            # Will be logged later in log_outcome_event when QC log exists
            return

        # Extract visit metadata from QC log
        visit_metadata = self.__extract_visit_metadata(qc_log_file, module)
        if not visit_metadata:
            log.warning(
                f"Could not extract visit metadata from {qc_log_file.name}. "
                f"Cannot log submit event."
            )
            return

        # Create proper key from metadata
        ptid = visit_metadata["ptid"]
        visit_date_str = visit_metadata["visit_date"].isoformat()
        key = VisitKey(ptid=ptid, visit_date=visit_date_str, module=module.upper())

        # Log submit event immediately
        submit_logged = False
        try:
            submit_event = VisitEvent(
                action="submit",
                pipeline_adcid=pipeline_adcid,
                project_label=project.label,
                center_label=project.group,
                gear_name="form-scheduler",
                ptid=ptid,
                visit_date=visit_metadata["visit_date"],
                visit_number=visit_metadata["visit_number"],
                datatype="form",
                module=module.upper(),
                packet=visit_metadata.get("packet"),
                timestamp=upload_timestamp,
            )
            self.__event_logger.log_event(submit_event)
            submit_logged = True
            log.info(
                f"Logged submit event for {ptid} visit {visit_metadata['visit_number']}"
            )
        except Exception as error:
            log.error(f"Error logging submit event: {error}", exc_info=True)

        # Store minimal data for outcome event logging
        self.__pending[key] = PendingVisitData(
            ptid=ptid,
            visit_date=visit_date_str,
            visit_number=visit_metadata["visit_number"],
            session_id="",  # Not needed
            acquisition_id="",  # Not needed
            module=module.upper(),
            project_label=project.label,
            center_label=project.group,
            pipeline_adcid=pipeline_adcid,
            upload_timestamp=upload_timestamp,
            submit_logged=submit_logged,
            csv_filename=file.name,
        )

    def log_outcome_event(
        self, *, file: FileEntry, module: str, pipeline_succeeded: bool
    ) -> None:
        """Log outcome event immediately after pipeline completes.

        Uses QC log file at PROJECT level to get visit metadata.
        Logs outcome event ("pass-qc" or "not-pass-qc") immediately.

        If submit event wasn't logged earlier (because QC log didn't exist yet),
        logs both submit and outcome events now.

        Args:
            file: The original CSV file (at PROJECT level)
            module: Module name
            pipeline_succeeded: Whether the pipeline completed successfully
        """
        # Get project from file's parent
        project_id = file.parent_ref.id
        project = self.__proxy.get_container_by_id(project_id)

        completion_timestamp = datetime.now()

        try:
            # Look for QC log file at PROJECT level
            qc_log_file = self.__find_qc_log_file(project, module)

            if not qc_log_file:
                log.warning(
                    f"No QC log file found for {file.name}. "
                    f"Pipeline failed before identifier-lookup created QC log. "
                    f"Cannot log events without visit metadata."
                )
                return

            # Extract visit metadata from QC log
            visit_metadata = self.__extract_visit_metadata(qc_log_file, module)
            if not visit_metadata:
                log.warning(f"Could not extract visit metadata from {qc_log_file.name}")
                return

            # Create proper key from metadata
            ptid = visit_metadata["ptid"]
            visit_date_str = visit_metadata["visit_date"].isoformat()
            key = VisitKey(ptid=ptid, visit_date=visit_date_str, module=module.upper())

            # Check if we have pending data for this visit
            pending = self.__pending.get(key)

            if not pending:
                log.info(
                    f"No pending data for visit {ptid} {visit_date_str}. "
                    f"This is a re-evaluation (not a new submission). "
                    f"Will log outcome event only."
                )
                # For re-evaluations, we still need to log the outcome event
                # but we don't have upload_timestamp, so we'll use current time
                # TODO: Support re-evaluation scenario fully
                return

            # Check if we need to log submit event (wasn't logged earlier)
            # This happens when QC log didn't exist at queue time
            if not pending.submit_logged:
                try:
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
                        f"visit {visit_metadata['visit_number']} "
                        f"(deferred from queue time)"
                    )
                except Exception as error:
                    log.error(f"Error logging submit event: {error}", exc_info=True)

            # Log outcome event immediately
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
                timestamp=completion_timestamp,
            )
            self.__event_logger.log_event(outcome_event)
            log.info(
                f"Logged {outcome_action} event for {visit_metadata['ptid']} "
                f"visit {visit_metadata['visit_number']}"
            )

        except Exception as error:
            log.error(
                f"Error logging outcome event: {error}",
                exc_info=True,
            )
        finally:
            # Clean up pending data
            if "key" in locals() and key in self.__pending:
                del self.__pending[key]

    def __find_qc_log_file(self, project: Project, module: str) -> Optional[FileEntry]:
        """Find the QC log file at PROJECT level.

        QC log files are created by identifier-lookup gear and follow pattern:
        {ptid}_{visitdate}_{module}_qc-status.log

        These files are more reliable than JSON files because they're created
        earlier in the pipeline and always exist at PROJECT level.

        Args:
            project: Project container
            module: Module name

        Returns:
            QC log FileEntry if found, None otherwise
        """
        # Pattern: {ptid}_{visitdate}_{module}_qc-status.log
        # Example: 110001_2024-01-15_UDS_qc-status.log
        qc_log_pattern = f"_{module.upper()}_qc-status.log"

        # Look for QC log files matching the module
        if not project.files:
            return None
        qc_log_files = [f for f in project.files if f.name.endswith(qc_log_pattern)]

        if not qc_log_files:
            return None

        # If multiple files, return the most recently modified
        # (handles case where multiple visits for same module)
        qc_log_files.sort(key=lambda f: f.modified, reverse=True)
        return qc_log_files[0]

    def __extract_visit_metadata(
        self, metadata_file: FileEntry, module: str
    ) -> Optional[Dict[str, Any]]:
        """Extract visit metadata from QC log or JSON file.

        QC log files have metadata directly in file.info.
        JSON files have metadata nested in file.info.forms.json.

        Args:
            metadata_file: QC log or JSON FileEntry with form metadata
            module: Module name

        Returns:
            Dict with ptid, visit_date, visit_number, packet if successful
        """
        # Check if this is a QC log file (metadata directly in info)
        # QC log pattern: {ptid}_{visitdate}_{module}_qc-status.log
        if metadata_file.name.endswith("_qc-status.log"):
            # QC log file - metadata is directly in file.info
            form_metadata = metadata_file.info
        else:
            # JSON file - metadata is nested in file.info.forms.json
            form_metadata = metadata_file.info.get("forms", {}).get("json", {})

        if not form_metadata:
            log.warning(f"No form metadata in {metadata_file.name}")
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
                f"Missing required fields in {metadata_file.name}: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"visitnum={visit_keys.visitnum}"
            )
            return None

        # Parse visit date using common date utility
        if not visit_keys.date:
            log.warning(f"Missing date in {metadata_file.name}")
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
