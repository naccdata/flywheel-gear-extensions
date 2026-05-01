"""Defines Pipeline Event Logger business logic."""

import logging
from datetime import datetime
from typing import Optional, cast

from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import FileVisitAnnotator, QCStatusLogManager
from event_capture.event_capture import VisitEventCapture
from event_capture.event_generator import create_visit_event
from event_capture.visit_events import VisitEventType
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import FileErrorList, QCStatus
from nacc_common.form_dates import DEFAULT_DATE_TIME_FORMAT
from pydantic import ValidationError

from .qc_reader import GearQC, QCErrorConfig

log = logging.getLogger(__name__)

# Mapping from QC status values to normalized outcome keys
_QC_STATUS_TO_OUTCOME_KEY: dict[QCStatus, str] = {
    "PASS": "pass",
    "FAIL": "fail",
    "IN REVIEW": "in-review",
}


class PipelineEventLogger:
    """Orchestrates QC log update and event capture for an upstream gear.

    Reads QC outcomes from file metadata written by an upstream gear,
    updates the project-level QC status log (attributed to the upstream
    gear), and optionally captures a VisitEvent to S3.
    """

    def __init__(
        self,
        *,
        file_entry: FileEntry,
        project: ProjectAdaptor,
        upstream_gear_name: str,
        event_capture: Optional[VisitEventCapture],
        event_actions: dict[str, str],
        error_configs: Optional[list[QCErrorConfig]] = None,
        dry_run: bool = False,
    ):
        self._file_entry = file_entry
        self._project = project
        self._upstream_gear_name = upstream_gear_name
        self._event_capture = event_capture
        self._event_actions = event_actions
        self._error_configs = error_configs
        self._dry_run = dry_run

    def run(self) -> None:
        """Execute the pipeline event logger workflow.

        Steps:
        1. Read GearQC from file.info.qc.{upstream_gear_name}
        2. Derive QC status and extract errors from check results
        3. Read DataIdentification from file.info.data_identification
        4. Resolve event timestamp
        5. Update project-level QC status log (non-critical)
        6. Capture VisitEvent to S3 (non-critical)
        """
        gear_qc = self._read_gear_qc()
        qc_status = self._get_status(gear_qc)
        errors = gear_qc.extract_errors(self._error_configs)
        log.info("QC status: %s, errors: %d", qc_status, len(errors))
        data_identification = self._read_data_identification()
        timestamp = self._resolve_timestamp()
        self._update_qc_status_log(data_identification, qc_status, errors)
        self._capture_event(qc_status, data_identification, timestamp)

    def _read_gear_qc(self) -> GearQC:
        """Read GearQC from file.info.qc.{upstream_gear_name}.

        Returns:
            GearQC instance for the upstream gear

        Raises:
            GearExecutionError: If QC metadata is missing or invalid
        """
        filename = self._file_entry.name
        log.info(
            "Reading QC metadata for gear '%s' from file %s",
            self._upstream_gear_name,
            filename,
        )
        return GearQC.from_file(self._file_entry, self._upstream_gear_name)

    def _get_status(self, gear_qc: GearQC) -> QCStatus:
        """Derive aggregate QC status from the GearQC object.

        Returns:
            The aggregate QCStatus

        Raises:
            GearExecutionError: If no valid QC states are found
        """
        status = gear_qc.status
        if status is None:
            raise GearExecutionError(
                f"No QC check results with valid state found for gear "
                f"'{self._upstream_gear_name}' on file {self._file_entry.name}"
            )
        return status

    def _read_data_identification(self) -> DataIdentification:
        """Read DataIdentification from file.info.data_identification.

        Returns:
            DataIdentification for the input file

        Raises:
            GearExecutionError: If data_identification is missing or invalid
        """
        filename = self._file_entry.name
        log.info("Reading data identification from file.info.data_identification")

        data_identification_dict = self._file_entry.info.get("data_identification")
        if not data_identification_dict:
            raise GearExecutionError(
                f"file.info.data_identification not found on input file {filename}"
            )

        try:
            return DataIdentification.from_visit_metadata(**data_identification_dict)
        except (ValidationError, ValueError, TypeError) as error:
            raise GearExecutionError(
                f"Invalid data_identification on file {filename}: {error}"
            ) from error

    def _resolve_timestamp(self) -> datetime:
        """Resolve the event timestamp from file metadata.

        Prefers validated-timestamp from file.info if present,
        otherwise falls back to file.modified.

        Returns:
            The resolved timestamp
        """
        validated_ts = self._file_entry.info.get("validated-timestamp")
        if validated_ts:
            log.info("Resolved timestamp: %s (from validated-timestamp)", validated_ts)
            return datetime.strptime(validated_ts, DEFAULT_DATE_TIME_FORMAT)

        timestamp = self._file_entry.modified
        log.info("Resolved timestamp: %s (from file.modified)", timestamp)
        return timestamp

    def _update_qc_status_log(
        self,
        data_identification: DataIdentification,
        qc_status: QCStatus,
        errors: FileErrorList,
    ) -> None:
        """Update project-level QC status log.

        Non-critical — logs warning on failure. Skipped in dry_run mode.
        """
        if self._dry_run:
            log.info("DRY RUN: Skipping QC status log update")
            return

        log.info("Updating QC status log")
        try:
            error_log_template = ErrorLogTemplate()
            visit_annotator = FileVisitAnnotator(project=self._project)
            qc_log_manager = QCStatusLogManager(
                error_log_template=error_log_template,
                visit_annotator=visit_annotator,
            )

            qc_log_filename = qc_log_manager.update_qc_log(
                visit_keys=data_identification,
                project=self._project,
                gear_name=self._upstream_gear_name,
                status=qc_status,
                errors=errors,
                add_visit_metadata=True,
            )

            if qc_log_filename:
                log.info("Successfully updated QC status log: %s", qc_log_filename)
            else:
                log.warning("Failed to update QC status log (non-critical)")
        except Exception as error:
            log.warning("Failed to update QC status log (non-critical): %s", error)

    def _capture_event(
        self,
        qc_status: QCStatus,
        data_identification: DataIdentification,
        timestamp: datetime,
    ) -> None:
        """Capture VisitEvent to S3 based on QC outcome.

        Non-critical — logs warning on failure. Skipped if event_capture
        is None or no matching action for the QC status. Skipped in
        dry_run mode.
        """
        if self._dry_run:
            log.info("DRY RUN: Skipping event capture")
            return

        if self._event_capture is None:
            return

        outcome_key = _QC_STATUS_TO_OUTCOME_KEY.get(qc_status)
        if outcome_key is None:
            log.warning("Unknown QC status '%s', skipping event capture", qc_status)
            return

        event_action = self._event_actions.get(outcome_key)
        if event_action is None:
            log.info(
                "No event action configured for outcome '%s', skipping event capture",
                outcome_key,
            )
            return

        log.info(
            "Capturing event: action=%s (QC outcome: %s)",
            event_action,
            outcome_key,
        )

        try:
            visit_event = create_visit_event(
                action=cast(VisitEventType, event_action),
                visit_metadata=data_identification,
                project=self._project,
                completion_time=timestamp,
                gear_name=self._upstream_gear_name,
            )

            if visit_event is None:
                log.warning(
                    "Failed to create visit event (non-critical): invalid project label"
                )
                return

            self._event_capture.capture_event(visit_event)
            log.info("Successfully captured event to S3")
        except Exception as error:
            log.warning("Failed to capture event to S3 (non-critical): %s", error)
