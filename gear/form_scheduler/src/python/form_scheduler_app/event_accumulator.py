"""Simplified event accumulator for QC-pass events only."""

import logging
from typing import Optional

from configs.ingest_configs import FormProjectConfigs
from deletions.models import DeleteInfoModel
from error_logging.error_logger import ErrorLogTemplate
from event_capture.event_capture import VisitEventCapture
from event_capture.event_generator import create_visit_event
from event_capture.visit_events import (
    ACTION_DELETE,
    ACTION_PASS_QC,
)
from event_capture.visit_extractor import DataIdentificationExtractor
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import (
    QC_STATUS_PASS,
    DataIdentification,
    FileQCModel,
)
from nacc_common.field_names import FieldNames
from pydantic import ValidationError

log = logging.getLogger(__name__)


class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""

    def __init__(
        self,
        event_capture: VisitEventCapture,
        form_configs: Optional[FormProjectConfigs] = None,
    ) -> None:
        """Initialize the simplified EventAccumulator.

        Args:
            event_capture: Logger for visit events
            form_configs: optional form module configs used to resolve the
                module-specific date field when extracting visit metadata from
                forms.json. Falls back to auto-detection when configs are not
                provided or the module is unknown.
        """
        self.__event_capture = event_capture
        self.__error_log_template = ErrorLogTemplate()
        self.__form_configs = form_configs

    def _date_field_for(self, json_file: FileEntry) -> Optional[str]:
        """Return the configured module-specific date field for the file.

        Reads the module from the file's forms.json metadata and looks up its
        date field in the form module configs. Returns None when configs are
        unavailable or the module is unknown, letting the extractor auto-detect
        the date column.

        Args:
            json_file: the JSON file with forms metadata

        Returns:
            the module-specific date field, or None if it cannot be resolved
        """
        if not self.__form_configs:
            return None

        try:
            json_file = json_file.reload()
            forms_json = (
                json_file.info.get("forms", {}).get("json", {})
                if json_file.info
                else {}
            )
        except Exception:  # best-effort; fall back to auto-detection
            return None

        module = forms_json.get(FieldNames.MODULE)
        if not module:
            return None

        module_configs = self.__form_configs.module_configs.get(module.upper())
        return module_configs.date_field if module_configs else None

    def create_qc_status_file_name(self, json_file: FileEntry) -> Optional[str]:
        """Creates the qc status log file from the form metadata for the file.

        Args:
          json_file: the JSON file with data
        Returns:
          the QC status file for the visit in the file.
        """
        # Extract DataIdentification from JSON file metadata
        data_id = DataIdentificationExtractor.from_json_file_metadata(
            json_file, date_field=self._date_field_for(json_file)
        )
        if not data_id:
            return None

        # Use ErrorLogTemplate to generate expected QC status log filename
        return self.__error_log_template.instantiate(data_id)

    def find_qc_status_for_json_file(
        self, json_file: FileEntry, project: ProjectAdaptor
    ) -> Optional[FileEntry]:
        """Find the QC status log for a JSON file at project level.

        Uses ErrorLogTemplate to generate possible QC status log filenames
        from the JSON file's forms.json metadata, then looks them up in project files.
        Tries new format first, then legacy format for backward compatibility.

        Args:
            json_file: The JSON file from acquisition (already in queue)
            project: The project containing QC status logs

        Returns:
            The corresponding QC status log file, or None if not found
        """
        # Extract DataIdentification from JSON file metadata
        data_id = DataIdentificationExtractor.from_json_file_metadata(
            json_file, date_field=self._date_field_for(json_file)
        )
        if not data_id:
            log.warning("Could not extract data identification for %s", json_file.name)
            return None

        # Try new format first (with visitnum and packet if present)
        new_format_filename = self.__error_log_template.instantiate(data_id)
        if new_format_filename:
            try:
                qc_file = project.get_file(new_format_filename)
                if qc_file:
                    return qc_file
            except Exception:
                # File not found, continue to legacy format
                pass

        # Try legacy format (without visitnum and packet)
        legacy_filename = self.__error_log_template.instantiate_legacy(data_id)
        if legacy_filename and legacy_filename != new_format_filename:
            try:
                qc_file = project.get_file(legacy_filename)
                if qc_file:
                    return qc_file
            except Exception:
                # File not found
                pass

        return None

    def _extract_visit_metadata(
        self, json_file: FileEntry, qc_log_file: Optional[FileEntry]
    ) -> Optional[DataIdentification]:
        """Extract visit metadata with priority: QC status custom info, then
        JSON file.

        Args:
            json_file: The JSON file from acquisition
            qc_log_file: The QC status log file (may be None)

        Returns:
            DataIdentification instance or None if extraction fails
        """
        # Try QC status custom info first
        if qc_log_file and qc_log_file.info:
            visit_metadata = DataIdentificationExtractor.from_qc_status_custom_info(
                qc_log_file.info
            )
            if visit_metadata:
                return visit_metadata

        # Fall back to JSON file metadata
        visit_metadata = DataIdentificationExtractor.from_json_file_metadata(
            json_file, date_field=self._date_field_for(json_file)
        )
        if visit_metadata:
            return visit_metadata

        return None

    def _check_qc_status(self, qc_log_file: FileEntry) -> bool:
        """Check if QC status is PASS and return completion timestamp.

        Assumes qc_log_file has already been reloaded by the caller so that
        its custom info is populated.

        Args:
            qc_log_file: The QC status log file

        Returns:
            QC completion timestamp if status is PASS, None otherwise
        """
        try:
            if not qc_log_file.info or "qc" not in qc_log_file.info:
                log.info("No QC metadata found in %s", qc_log_file.name)
                return False
            qc_model = FileQCModel.model_validate(qc_log_file.info)
        except ValidationError as err:
            log.warning("Failed to parse QC metadata for %s: %s", qc_log_file.name, err)
            return False

        # Check if QC status is PASS
        file_status = qc_model.get_file_status()
        return file_status == QC_STATUS_PASS

    def capture_qc_event(self, json_file: FileEntry, project: ProjectAdaptor) -> None:
        """Log QC-pass events for a JSON file if it passes QC validation.

        Args:
            json_file: JSON file from finalization queue
            project: The project containing QC status logs
        """
        # Validate inputs
        if not json_file:
            log.warning("JSON file is None, skipping event logging")
            return
        if not project:
            log.warning("Project is None, skipping event logging")
            return

        try:
            # Find corresponding QC status log
            qc_log_file = self.find_qc_status_for_json_file(json_file, project)
            if not qc_log_file:
                log.warning("Failed to find the error log file for %s", json_file.name)
                return

            # Reload to get the latest file.info from Flywheel.
            qc_log_file = qc_log_file.reload()

            # Check QC status - only proceed if PASS
            if not self._check_qc_status(qc_log_file):
                log.info("QC status is not PASS for %s", json_file.name)
                return

            # Extract visit metadata
            visit_metadata = self._extract_visit_metadata(json_file, qc_log_file)
            if not visit_metadata:
                log.warning(
                    "Could not extract valid visit metadata for %s", json_file.name
                )
                return

            # Create and log QC-pass event
            timestamp = (
                json_file.info.get("validated-timestamp") if json_file.info else None
            )
            visit_event = create_visit_event(
                action=ACTION_PASS_QC,
                visit_metadata=visit_metadata,
                project=project,
                completion_time=timestamp if timestamp else qc_log_file.modified,
                gear_name="form-qc-checker",
            )
            if visit_event:
                self.__event_capture.capture_event(visit_event)
                log.info("Logged QC-pass event for %s", json_file.name)
                return

            log.warning("Failed to create visit event for %s", json_file.name)

        except Exception as e:
            # Log error but don't fail pipeline processing
            log.error(
                "Error logging events for %s: %s", json_file.name, e, exc_info=True
            )

    def capture_delete_event(
        self, request_file: FileEntry, project: ProjectAdaptor
    ) -> None:
        """Capture a delete event when form-deletion gear succeeds.

        Checks file.info.state in the input file custom info set by the
        form-deletion gear. Only captures an event if state is 'PASS'.

        Args:
            request_file: The deletion request file processed by form-deletion
            project: The project containing the deletion request
        """
        if not request_file:
            log.warning("Request file is None, skipping delete event")
            return
        if not project:
            log.warning("Project is None, skipping delete event")
            return

        try:
            # Reload to get latest state written by form-deletion gear
            request_file = request_file.reload()

            delete_info = (
                DeleteInfoModel.model_validate(request_file.info)
                if request_file.info
                else None
            )

            if not delete_info or delete_info.delete_response.state != "PASS":
                log.info(
                    "Skipping failed or incomplete delete event for %s",
                    request_file.name,
                )
                return

            data_id = DataIdentificationExtractor.from_deletion_request_file(
                request_file=request_file,
                adcid=project.get_pipeline_adcid(),
            )
            if not data_id:
                log.warning(
                    "Could not extract data identification for %s", request_file.name
                )
                return

            visit_event = create_visit_event(
                action=ACTION_DELETE,
                visit_metadata=data_id,
                project=project,
                completion_time=delete_info.processed_timestamp
                if delete_info.processed_timestamp
                else request_file.modified,
                gear_name="form-deletion",
            )
            if visit_event:
                self.__event_capture.capture_event(visit_event)
                log.info("Captured delete event for %s", request_file.name)
                return

            log.warning("Failed to create delete event for %s", request_file.name)
        except ValidationError as error:
            log.error(
                "Error validating delete response for %s: %s", request_file.name, error
            )
        except Exception as e:
            log.error(
                "Error capturing delete event for %s: %s",
                request_file.name,
                e,
                exc_info=True,
            )
