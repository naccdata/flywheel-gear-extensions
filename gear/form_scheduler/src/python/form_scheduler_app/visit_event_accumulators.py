"""Visit event accumulators using QC report visitor pattern.

This module adapts the ProjectReportVisitor pattern from gather_submission_status
for event logging. The key difference is that we only need to find the FIRST
gear run that fails (or succeeds), not all of them.

Strategy:
1. Submission pipeline: Get upload timestamp from CSV, then check QC status logs
2. Finalization pipeline: Check QC status logs first, then access file.info.forms.json
"""

import logging
import re
from datetime import datetime
from typing import Optional, Set

from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCVisitor,
    ValidationModel,
    VisitKeys,
)
from nacc_common.module_types import ModuleName
from pydantic import BaseModel, ConfigDict, ValidationError

log = logging.getLogger(__name__)


class VisitKey(BaseModel):
    """Composite key for uniquely identifying a visit."""

    model_config = ConfigDict(frozen=True)

    ptid: str
    visit_date: str
    module: str


class FirstErrorVisitor(QCVisitor):
    """Finds the FIRST FileError in QC metadata.

    Unlike ErrorReportVisitor which finds all errors, this visitor stops
    after finding the first error to get timestamp and gear info.
    """

    def __init__(self) -> None:
        self.__gear_name: Optional[str] = None
        self.__first_error: Optional[FileError] = None

    @property
    def gear_name(self) -> Optional[str]:
        """Returns the gear name where first error was found."""
        return self.__gear_name

    @property
    def first_error(self) -> Optional[FileError]:
        """Returns the first error found."""
        return self.__first_error

    def visit_file_model(self, file_model: FileQCModel) -> None:
        """Visit file model and stop after finding first error."""
        for gear_name, gear_model in file_model.qc.items():
            if self.__first_error is not None:
                return
            self.__gear_name = gear_name
            gear_model.apply(self)

    def visit_gear_model(self, gear_model: GearQCModel) -> None:
        """Visit gear model."""
        if self.__first_error is not None:
            gear_model.validation.apply(self)

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Visit validation model and check for errors."""
        if self.__first_error is not None:
            return

        state = validation_model.state
        if state is not None and state.lower() == "pass":
            return

        # Found a non-pass state, get first error if available
        if validation_model.data:
            validation_model.data[0].apply(self)

    def visit_file_error(self, file_error: FileError) -> None:
        """Capture the first error."""
        if self.__first_error is not None:
            self.__first_error = file_error

    def visit_cleared_alert(self, cleared_alert: ClearedAlertModel) -> None:
        """Not needed for event logging."""
        pass

    def visit_alert_provenance(self, alert_provenance: ClearedAlertProvenance) -> None:
        """Not needed for event logging."""
        pass


class SubmissionEventAccumulator:
    """Accumulates events for submission pipeline using QC status logs.

    Strategy:
    1. Get upload timestamp from CSV file
    2. Find QC status log files for this module
    3. Use FirstErrorVisitor to extract metadata from first error
    4. Log submit + not-pass-qc events
    5. Track logged visits to prevent duplicates
    """

    def __init__(
        self,
        event_logger: VisitEventLogger,
        modules: Optional[Set[ModuleName]] = None,
    ):
        self.__event_logger = event_logger
        self.__modules = modules
        self._logged_submits: Set[VisitKey] = set()

        # Pattern for QC status log files
        pattern = r"^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$"
        self.__matcher = re.compile(pattern)

    @property
    def logged_submits(self) -> Set[VisitKey]:
        """Get set of logged visits (for finalization accumulator)."""
        return self._logged_submits

    def __get_visit_key(self, filename: str) -> Optional[VisitKeys]:
        """Extract visit keys from QC status log filename.

        Args:
            filename: QC status log filename

        Returns:
            VisitKeys if filename matches pattern and module is valid
        """
        match = self.__matcher.match(filename)
        if not match:
            return None

        ptid = match.group(1)
        visitdate = match.group(2)
        module = match.group(3).upper()

        if self.__modules is not None and module not in self.__modules:
            return None

        return VisitKeys(ptid=ptid, date=visitdate, module=module)

    def log_events(
        self, *, file: FileEntry, module: str, project: ProjectAdaptor
    ) -> None:
        """Log events if submission pipeline had failures.

        Args:
            file: CSV file at PROJECT level
            module: Module name
            project: Project adaptor
        """
        # Get upload timestamp from CSV file
        upload_timestamp = file.created

        # Find QC status log files with errors
        qc_logs_with_errors = self.__find_qc_logs_with_errors(
            module=module, project=project, after_timestamp=file.modified
        )

        if not qc_logs_with_errors:
            log.info(
                f"No QC log errors found for {file.name}. "
                f"Events will be logged during finalization."
            )
            return

        # Log events for each failed visit
        for qc_log in qc_logs_with_errors:
            self.__log_events_for_qc_log(qc_log, upload_timestamp, project)

    def __find_qc_logs_with_errors(
        self, module: str, project: ProjectAdaptor, after_timestamp: datetime
    ) -> list[FileEntry]:
        """Find QC status log files with errors."""
        qc_log_pattern = f"_{module.upper()}_qc-status.log"

        # Reload project to get latest files
        project = project.reload()

        # Find matching QC log files created after timestamp
        qc_logs = [
            f
            for f in project.files
            if f.name.endswith(qc_log_pattern) and f.modified >= after_timestamp
        ]

        # Filter to only those with errors
        qc_logs_with_errors = []
        for qc_log in qc_logs:
            if self.__has_qc_errors(qc_log):
                qc_logs_with_errors.append(qc_log)

        return qc_logs_with_errors

    def __has_qc_errors(self, qc_log: FileEntry) -> bool:
        """Check if QC log file has any errors."""
        try:
            qc_model = FileQCModel.model_validate(qc_log.info)
            status = qc_model.get_file_status()
            return status != "PASS"
        except Exception:
            return False

    def __log_events_for_qc_log(
        self, qc_log: FileEntry, upload_timestamp: datetime, project: ProjectAdaptor
    ) -> None:
        """Log events for a single QC status log file.

        Args:
            qc_log: QC status log file
            upload_timestamp: When CSV was uploaded
            project: Project adaptor
        """
        # Extract visit keys from filename
        visit_keys = self.__get_visit_key(qc_log.name)
        if not visit_keys:
            log.warning(f"Could not extract visit keys from {qc_log.name}")
            return

        # Reload file to get latest QC data
        qc_log = qc_log.reload()

        try:
            qc_model = FileQCModel.model_validate(qc_log.info)
        except ValidationError as error:
            log.warning(f"Failed to load QC data for {qc_log.name}: {error}")
            return

        # Use FirstErrorVisitor to get first error details
        error_visitor = FirstErrorVisitor()
        qc_model.apply(error_visitor)

        first_error = error_visitor.first_error
        gear_name = error_visitor.gear_name

        if not first_error or not gear_name:
            log.warning(f"No error details found in {qc_log.name}")
            return

        # Extract timestamp from error if available
        error_timestamp = None
        if first_error.timestamp:
            try:
                error_timestamp = datetime.strptime(
                    first_error.timestamp, "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                log.warning(f"Could not parse timestamp: {first_error.timestamp}")

        # Get pipeline_adcid
        pipeline_adcid = project.get_pipeline_adcid()
        if not pipeline_adcid:
            log.warning(f"No pipeline_adcid in project {project.label}")
            return

        # Create submit event
        # Note: packet is not available in FileError, would need to be extracted
        # from file.info.forms.json if needed
        submit_event = VisitEvent(
            action="submit",
            pipeline_adcid=pipeline_adcid,
            project_label=project.label,
            center_label=project.group,
            gear_name=gear_name,
            ptid=visit_keys.ptid or "",
            visit_date=visit_keys.date or "",
            visit_number=first_error.visitnum or "",
            datatype="form",
            module=visit_keys.module,  # type: ignore
            packet=None,  # TODO: Extract from file.info.forms.json if needed
            timestamp=upload_timestamp,
        )
        self.__event_logger.log_event(submit_event)

        # Create not-pass-qc event
        outcome_event = VisitEvent(
            action="not-pass-qc",
            pipeline_adcid=pipeline_adcid,
            project_label=project.label,
            center_label=project.group,
            gear_name=gear_name,
            ptid=visit_keys.ptid or "",
            visit_date=visit_keys.date or "",
            visit_number=first_error.visitnum or "",
            datatype="form",
            module=visit_keys.module,  # type: ignore
            packet=None,  # TODO: Extract from file.info.forms.json if needed
            timestamp=error_timestamp or datetime.now(),
        )
        self.__event_logger.log_event(outcome_event)

        # Track logged visit
        key = VisitKey(
            ptid=visit_keys.ptid or "",
            visit_date=visit_keys.date or "",
            module=visit_keys.module or "",
        )
        self._logged_submits.add(key)

        log.info(
            f"Logged submission failure events for {visit_keys.ptid} "
            f"visit {first_error.visitnum}"
        )


class FinalizationEventAccumulator:
    """Accumulates events for finalization pipeline.

    Strategy:
    1. Check QC status logs first (for metadata and status)
    2. Access file.info.forms.json from JSON file (for additional fields)
    3. Log submit (if not already logged) + outcome events
    """

    def __init__(
        self,
        event_logger: VisitEventLogger,
        modules: Optional[Set[ModuleName]] = None,
        submission_accumulator: Optional[SubmissionEventAccumulator] = None,
    ):
        self.__event_logger = event_logger
        self.__modules = modules
        self._submission_accumulator = submission_accumulator

        # Pattern for QC status log files
        pattern = r"^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$"
        self.__matcher = re.compile(pattern)

    def __get_visit_key(self, filename: str) -> Optional[VisitKeys]:
        """Extract visit keys from QC status log filename."""
        match = self.__matcher.match(filename)
        if not match:
            return None

        ptid = match.group(1)
        visitdate = match.group(2)
        module = match.group(3).upper()

        if self.__modules is not None and module not in self.__modules:
            return None

        return VisitKeys(ptid=ptid, date=visitdate, module=module)

    def log_events(
        self, *, file: FileEntry, module: str, project: ProjectAdaptor
    ) -> None:
        """Log events after finalization pipeline completes.

        Args:
            file: JSON file at ACQUISITION level
            module: Module name
            project: Project adaptor
        """
        # TODO: Implement finalization event logging
        # 1. Find corresponding QC status log file
        # 2. Use FirstErrorVisitor or check overall status
        # 3. Extract additional metadata from file.info.forms.json
        # 4. Check if submit already logged
        # 5. Log submit (if needed) + outcome events
        log.info(f"Finalization event logging not yet implemented for {file.name}")


def create_event_accumulator(
    pipeline_name: str,
    event_logger: VisitEventLogger,
    modules: Optional[Set[ModuleName]] = None,
    submission_accumulator: Optional[SubmissionEventAccumulator] = None,
) -> Optional[SubmissionEventAccumulator | FinalizationEventAccumulator]:
    """Create appropriate accumulator for pipeline type.

    Args:
        pipeline_name: Name of the pipeline ("submission" or "finalization")
        event_logger: Event logger
        modules: Set of valid module names
        submission_accumulator: Submission accumulator (for finalization)

    Returns:
        Pipeline-specific accumulator or None if unsupported pipeline
    """
    if pipeline_name == "submission":
        return SubmissionEventAccumulator(
            event_logger=event_logger,
            modules=modules,
        )
    elif pipeline_name == "finalization":
        return FinalizationEventAccumulator(
            event_logger=event_logger,
            modules=modules,
            submission_accumulator=submission_accumulator,
        )
    else:
        log.warning(f"Unknown pipeline type: {pipeline_name}")
        return None
