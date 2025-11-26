"""Pipeline-specific event accumulators for logging visit events.

This module provides polymorphic event accumulators that handle logging
for different pipeline types (submission and finalization).
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Set

from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent, VisitEventType
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.model import PTID_PATTERN
from keys.types import DatatypeNameType
from nacc_common.error_models import (
    ClearedAlertModel,
    ClearedAlertProvenance,
    FileError,
    FileQCModel,
    GearQCModel,
    QCVisitor,
    ValidationModel,
)
from nacc_common.field_names import FieldNames
from nacc_common.module_types import ModuleName
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)


class VisitKey(BaseModel):
    """Composite key for uniquely identifying a visit.

    Aligns with QC log file naming pattern: {ptid}_{visitdate}_{module}_qc-status.log

    Note: There is only one visit per year per participant at a center (ADCID).
    However, each visit can have multiple modules (UDS, FTLD, LBD, etc.).
    """

    model_config = ConfigDict(frozen=True)

    ptid: str
    visit_date: str
    module: str


class FileErrorContext(FileError):
    gear_name: str


class VisitStatus(BaseModel):
    """Data model used to accumulate visit information need to create a
    VisitEvent."""

    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)
    visit_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    module: ModuleName
    visit_number: Optional[str] = None
    packet: Optional[str] = None
    gear_name: Optional[str] = None
    timestamp: Optional[datetime] = None

    def update(self, file_error: FileErrorContext) -> None:
        self.gear_name = file_error.gear_name
        self.visit_number = file_error.visitnum
        self.timestamp = (
            datetime.strptime(file_error.timestamp, "%Y-%m-%d %H:%M:%S")
            if file_error.timestamp
            else None
        )

    def create_visit_key(self) -> VisitKey:
        return VisitKey(ptid=self.ptid, visit_date=self.visit_date, module=self.module)

    def create_visit_event(
        self,
        action: VisitEventType,
        project: ProjectAdaptor,
        datatype: DatatypeNameType,
    ) -> Optional[VisitEvent]:
        pipeline_adcid = project.get_pipeline_adcid()
        if not pipeline_adcid:
            log.warning("No pipeline_adcid in project %s", project.label)
            return None
        if not self.gear_name:
            log.warning("No gear name known for %s event for %s", action, self.ptid)
            return None
        if not self.visit_number:
            log.warning("No visit number known for %s event for %s", action, self.ptid)
            return None
        if not self.timestamp:
            log.warning("No timestamp for %s event for %s", action, self.ptid)
            return None

        return VisitEvent(
            action=action,
            pipeline_adcid=pipeline_adcid,
            project_label=project.label,
            center_label=project.group,
            gear_name=self.gear_name,
            ptid=self.ptid,
            visit_date=self.visit_date,
            visit_number=self.visit_number,
            datatype=datatype,
            module=self.module,
            packet=self.packet,
            timestamp=self.timestamp,
        )


class FileErrorVisitor(QCVisitor):
    """Finds the "first" FileError object."""

    def __init__(self) -> None:
        self.__file_error: Optional[FileErrorContext] = None
        self.__gear_name: Optional[str] = None

    def get_error_context(self) -> Optional[FileErrorContext]:
        return self.__file_error

    def visit_file_model(self, file_model: FileQCModel) -> None:
        for gear_name, gear_model in file_model.qc.items():
            self.__gear_name = gear_name
            gear_model.apply(self)
            self.__gear_name = None

            if self.__file_error is not None:
                return

    def visit_gear_model(self, gear_model: GearQCModel) -> None:
        gear_model.validation.apply(self)

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        if not validation_model.data:
            return

        validation_model.data[0].apply(self)

    def visit_file_error(self, file_error: FileError) -> None:
        error_model = file_error.model_dump()
        error_model["gear_name"] = self.__gear_name
        self.__file_error = FileErrorContext.model_validate(error_model)

    def visit_alert_provenance(self, alert_provenance: ClearedAlertProvenance) -> None:
        return

    def visit_cleared_alert(self, cleared_alert: ClearedAlertModel) -> None:
        return


class PipelineFileError(Exception):
    """Error for unexpected files."""


class PipelineEventAccumulator(ABC):
    """Abstract base class for pipeline-specific event accumulators.

    Provides common functionality for extracting metadata and logging
    events, with pipeline-specific implementations for when to log.
    """

    def __init__(
        self,
        event_logger: VisitEventLogger,
        modules: Optional[set[ModuleName]] = None,
    ):
        """Initialize the accumulator.

        Args:
            event_logger: Logger for writing events to S3
            module_configs: Dictionary of module configurations keyed by module name
            proxy: Flywheel proxy for querying containers
        """
        self.__event_logger = event_logger
        self.__modules = modules

    @abstractmethod
    def log_events(
        self, *, file: FileEntry, module: str, project: ProjectAdaptor
    ) -> None:
        """Log events after pipeline completes.

        Args:
            file: The file being processed
            module: Module name
            project: Project adaptor
        """

    def _log_submit_event(
        self, file: FileEntry, visit: VisitStatus, project: ProjectAdaptor
    ) -> None:
        """Log submit event.

        Args:
            file: File to use for timestamp (CSV or JSON)
            metadata: Visit metadata dict
            project: Project adaptor
        """
        submit_event = visit.create_visit_event(
            action="submit", project=project, datatype="form"
        )
        if submit_event is None:
            return

        self.__event_logger.log_event(submit_event)

    def _log_outcome_event(
        self, action: VisitEventType, visit: VisitStatus, project: ProjectAdaptor
    ) -> None:
        """Log outcome event (pass-qc or not-pass-qc).

        Args:
            action: Event action ("pass-qc" or "not-pass-qc")
            metadata: Visit metadata dict
            project: Project adaptor
        """
        outcome_event = visit.create_visit_event(
            action=action, project=project, datatype="form"
        )
        if outcome_event is None:
            return
        self.__event_logger.log_event(outcome_event)


class SubmissionEventAccumulator(PipelineEventAccumulator):
    """Logs events for submission pipeline (only if failures occurred).

    Tracks logged visits to prevent duplicate submit events in
    finalization pipeline.
    """

    def __init__(
        self, event_logger: VisitEventLogger, modules: Optional[set[ModuleName]] = None
    ):
        super().__init__(event_logger, modules)
        self._logged_submits: Set[VisitKey] = set()

        pattern = r"^([!-~]{1,10})_(\d{4}-\d{2}-\d{2})_(\w+)_qc-status.log$"
        self.__matcher = re.compile(pattern)

    # TODO: this duplicates code in nacc_common.qc_report
    def __get_visit_key(self, filename: str) -> VisitStatus:
        """Returns a VisitKeys object with ptid, module and visit date set
        extracted from a qc-status log filename.

        Additionally, checks that ptid and module correspond to those in this
        visitor.

        Args:
          filename: the filename
        Returns:
          the visit keys object with values set if filename matches the log
          filename pattern.
          None, otherwise.
        Raises:
          PipelineFileError if the name does not match the qc log file pattern
        """
        match = self.__matcher.match(filename)
        if not match:
            raise PipelineFileError(f"Expected QC status log, got {filename}")

        ptid = match.group(1)
        module = match.group(3).upper()
        if self.__modules is not None and module.upper() not in self.__modules:
            raise PipelineFileError(
                f"Unexpected module name in QC log file name {filename}"
            )

        visitdate = match.group(2)

        try:
            return VisitStatus(ptid=ptid, visit_date=visitdate, module=module)  # type: ignore
        except ValidationError as error:
            raise PipelineFileError(
                f"Expected QC status log, got {filename}"
            ) from error

    # TODO: this duplicates code in nacc_common qc_report
    def __extract_metadata(self, file: FileEntry) -> Optional[VisitStatus]:
        """Extract visit metadata from file.

        Works with both QC log files (PROJECT level) and JSON files (ACQUISITION level).

        Args:
            file: QC log FileEntry
            module: Module name

        Returns:
            Dict with ptid, visit_date, visit_number, packet if successful
        """
        visit = self.__get_visit_key(file.name)

        file = file.reload()

        try:
            qc_model = FileQCModel.model_validate(file.info)
        except ValidationError as error:
            log.warning("Failed to load QC data for %s: %s", file.name, error)
            return None

        error_visitor = FileErrorVisitor()
        qc_model.apply(error_visitor)

        file_error = error_visitor.get_error_context()
        if file_error is None:
            log.warning("No error data found for %s", file.name)
            return None

        visit.update(file_error)

        # Validate required fields
        if not all([visit.ptid, visit.visit_number]):
            log.warning(
                f"Missing required fields in {file.name}: "
                f"ptid={visit.ptid}, "
                f"visitnum={visit.visit_number}"
            )
            return None

        return visit

    def log_events(
        self, *, file: FileEntry, module: str, project: ProjectAdaptor
    ) -> None:
        """Log events if submission pipeline had failures.

        Only logs if QC log files contain errors with visit metadata.

        Args:
            file: CSV file at PROJECT level
            module: Module name
            project: Project adaptor
        """
        # Find QC log files with errors for this module
        qc_logs_with_errors = self._find_qc_logs_with_errors(
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
            try:
                visit_metadata = self.__extract_metadata(qc_log)
                if not visit_metadata:
                    continue

                # Log submit event (timestamp = CSV upload time)
                self._log_submit_event(file, visit_metadata, project)

                # Log not-pass-qc event (timestamp = current time)
                self._log_outcome_event("not-pass-qc", visit_metadata, project)

                # Track to prevent duplicate in finalization
                key = VisitKey(
                    ptid=visit_metadata.ptid,
                    visit_date=visit_metadata.visit_date,
                    module=module.upper(),
                )
                self._logged_submits.add(key)

                log.info(
                    "Logged submission failure events for %s visit %s",
                    visit_metadata.ptid,
                    visit_metadata.visit_number,
                )

            except Exception as error:
                log.error(
                    f"Error logging events for {qc_log.name}: {error}", exc_info=True
                )

    @property
    def logged_submits(self) -> Set[VisitKey]:
        """Get set of logged visits (for finalization accumulator).

        Returns:
            Set of VisitKey tuples for visits that have been logged
        """
        return self._logged_submits

    def _find_qc_logs_with_errors(
        self, module: str, project: ProjectAdaptor, after_timestamp: datetime
    ) -> List[FileEntry]:
        """Find QC log files with errors for this module.

        Args:
            module: Module name
            project: Project adaptor
            after_timestamp: Only return files modified after this time

        Returns:
            List of QC log FileEntry objects with errors
        """
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
            if self._has_qc_errors(qc_log):
                qc_logs_with_errors.append(qc_log)

        return qc_logs_with_errors

    def _has_qc_errors(self, qc_log: FileEntry) -> bool:
        """Check if QC log file has any errors.

        Args:
            qc_log: QC log file entry

        Returns:
            True if file has QC errors (status != PASS)
        """
        try:
            qc_model = FileQCModel.model_validate(qc_log.info)
            status = qc_model.get_file_status()
            return status != "PASS"
        except Exception:
            return False


class FinalizationEventAccumulator(PipelineEventAccumulator):
    """Logs events for finalization pipeline (always).

    Checks if submit event was already logged during submission pipeline
    to avoid duplicates.
    """

    def __init__(
        self,
        *args,
        submission_accumulator: Optional[SubmissionEventAccumulator] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._submission_accumulator = submission_accumulator

    def __extract_metadata(self, file: FileEntry) -> Optional[VisitStatus]:
        """Extract visit metadata from JSON file.

        Args:
            file: JSON file at ACQUISITION level

        Returns:
            VisitStatus object populated from file.info.forms.json
        """
        if not file.name.endswith(".json"):
            raise PipelineFileError(
                f"Cannot get metadata from non-JSON file {file.name}"
            )

        file = file.reload()

        # Get form metadata from file.info.forms.json
        forms_data = file.info.get("forms", {})
        form_metadata = forms_data.get("json", {})

        if not form_metadata:
            log.warning(f"No forms.json metadata in {file.name}")
            return None

        # Extract required fields
        ptid = form_metadata.get(FieldNames.PTID)
        visitnum = form_metadata.get(FieldNames.VISITNUM)
        visitdate = form_metadata.get(FieldNames.DATE_COLUMN)
        module = form_metadata.get(FieldNames.MODULE)

        # Extract optional fields
        packet = form_metadata.get(FieldNames.PACKET)

        # Validate required fields
        if not all([ptid, visitdate, module]):
            log.warning(
                f"Missing required fields in {file.name}: "
                f"ptid={ptid}, visitdate={visitdate}, module={module}"
            )
            return None

        # Note: visitnum may be missing - this is acceptable for some modules
        if not visitnum:
            log.info(
                f"No visit number in {file.name} - may be expected for this module"
            )

        # Note: packet may be missing - this is acceptable
        if not packet:
            log.debug(f"No packet in {file.name}")

        # Note: gear_name and timestamp will need to be set separately
        # These come from QC metadata, not form metadata

        try:
            visit_status = VisitStatus(
                ptid=ptid,
                visit_date=visitdate,
                module=module,  # type: ignore
                visit_number=visitnum,
                packet=str(packet) if packet else None,
                gear_name=None,  # TODO: Extract from QC metadata
                timestamp=None,  # TODO: Extract from QC metadata or file timestamps
            )
            return visit_status
        except ValidationError as error:
            log.warning(f"Failed to create VisitStatus from {file.name}: {error}")
            return None

    def log_events(
        self, *, file: FileEntry, module: str, project: ProjectAdaptor
    ) -> None:
        """Log events after finalization pipeline completes.

        Always logs events (visit metadata available in JSON file).
        Checks if submit already logged during submission.

        Args:
            file: JSON file at ACQUISITION level
            module: Module name
            project: Project adaptor
        """
        try:
            # Extract metadata from JSON file
            metadata = self.__extract_metadata(file)
            if not metadata:
                log.warning(f"Could not extract metadata from {file.name}")
                return

            # Check if submit already logged during submission
            key = VisitKey(
                ptid=metadata.ptid,
                visit_date=metadata.visit_date,
                module=module.upper(),
            )
            already_logged = (
                self._submission_accumulator
                and key in self._submission_accumulator.logged_submits
            )

            # Log submit if not already logged
            if not already_logged:
                self._log_submit_event(file, metadata, project)
                log.info(
                    "Logged submit event for %s visit %s",
                    metadata.ptid,
                    metadata.visit_number,
                )
            else:
                log.info(
                    "Skipping submit event for %s visit %s (already logged)",
                    metadata.ptid,
                    metadata.visit_number,
                )

            # Always log outcome
            status = self._get_file_status(file)
            action: VisitEventType = "pass-qc" if status == "PASS" else "not-pass-qc"
            self._log_outcome_event(action, metadata, project)

            log.info(
                "Logged %s event for %s visit %s",
                {action},
                metadata.ptid,
                metadata.visit_number,
            )

        except Exception as error:
            log.error(
                f"Error logging finalization events for {file.name}: {error}",
                exc_info=True,
            )

    def _get_file_status(self, file: FileEntry) -> str:
        """Get overall QC status from JSON file.

        Args:
            file: JSON file entry

        Returns:
            Overall QC status ("PASS", "FAIL", or "IN REVIEW")
        """
        try:
            qc_model = FileQCModel.model_validate(file.info)
            return qc_model.get_file_status()
        except Exception as error:
            log.warning(f"Failed to get file status: {error}")
            return "FAIL"  # Default to FAIL if can't determine


def create_event_accumulator(
    pipeline_name: str,
    event_logger: VisitEventLogger,
    submission_accumulator: Optional[SubmissionEventAccumulator] = None,
) -> Optional[PipelineEventAccumulator]:
    """Create appropriate accumulator for pipeline type.

    Factory function that instantiates the correct accumulator based on
    pipeline name.

    Args:
        pipeline_name: Name of the pipeline ("submission" or "finalization")
        event_logger: Event logger
        module_configs: Module configurations
        proxy: Flywheel proxy
        submission_accumulator: Submission accumulator (for finalization)

    Returns:
        Pipeline-specific accumulator or None if unsupported pipeline
    """
    if pipeline_name == "submission":
        return SubmissionEventAccumulator(
            event_logger=event_logger,
        )
    elif pipeline_name == "finalization":
        return FinalizationEventAccumulator(
            event_logger=event_logger,
            submission_accumulator=submission_accumulator,
        )
    else:
        log.warning(f"Unknown pipeline type: {pipeline_name}")
        return None
