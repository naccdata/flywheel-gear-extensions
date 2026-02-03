"""Simplified event accumulator for QC-pass events only."""

import logging
from datetime import datetime
from typing import Optional

from error_logging.error_logger import ErrorLogTemplate
from event_capture.event_capture import VisitEventCapture
from event_capture.visit_events import ACTION_PASS_QC, VisitEvent
from event_capture.visit_extractor import VisitMetadataExtractor
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import (
    QC_STATUS_PASS,
    FileQCModel,
    VisitMetadata,
)
from pipeline.pipeline_label import PipelineLabel
from pydantic import ValidationError

log = logging.getLogger(__name__)


class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""

    def __init__(self, event_capture: VisitEventCapture) -> None:
        """Initialize the simplified EventAccumulator.

        Args:
            event_capture: Logger for visit events
            datatype: Type of data being processed (default: "form")
        """
        self.__event_capture = event_capture
        self.__error_log_template = ErrorLogTemplate()

    def create_qc_status_file_name(self, json_file: FileEntry) -> Optional[str]:
        """Creates the qc status log file from the form metadata for the file.

        Args:
          json_file: the JSON file with data
        Returns:
          the QC status file for the visit in the file.
        """
        if not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        module = forms_json.get("module")
        if not module:
            return None

        # Use ErrorLogTemplate to generate expected QC status log filename
        return self.__error_log_template.instantiate(record=forms_json, module=module)

    def find_qc_status_for_json_file(
        self, json_file: FileEntry, project: ProjectAdaptor
    ) -> Optional[FileEntry]:
        """Find the QC status log for a JSON file at project level.

        Uses ErrorLogTemplate to generate the expected QC status log filename
        from the JSON file's forms.json metadata, then looks it up in project files.

        Args:
            json_file: The JSON file from acquisition (already in queue)
            project: The project containing QC status logs

        Returns:
            The corresponding QC status log file, or None if not found
        """
        qc_log_name = self.create_qc_status_file_name(json_file)
        if not qc_log_name:
            return None

        # Look up the QC status log file by name in project files
        try:
            return project.get_file(qc_log_name)
        except Exception:
            # get_file might raise various exceptions depending on implementation
            return None

    def _extract_visit_metadata(
        self, json_file: FileEntry, qc_log_file: Optional[FileEntry]
    ) -> Optional[VisitMetadata]:
        """Extract visit metadata with priority: QC status custom info, then
        JSON file.

        Args:
            json_file: The JSON file from acquisition
            qc_log_file: The QC status log file (may be None)

        Returns:
            VisitMetadata instance or None if extraction fails
        """
        # Try QC status custom info first
        if qc_log_file and qc_log_file.info:
            visit_metadata = VisitMetadataExtractor.from_qc_status_custom_info(
                qc_log_file.info
            )
            if visit_metadata and VisitMetadataExtractor.is_valid_for_event(
                visit_metadata
            ):
                return visit_metadata

        # Fall back to JSON file metadata
        visit_metadata = VisitMetadataExtractor.from_json_file_metadata(json_file)
        if visit_metadata and VisitMetadataExtractor.is_valid_for_event(visit_metadata):
            return visit_metadata

        return None

    def _check_qc_status(self, qc_log_file: FileEntry) -> bool:
        """Check if QC status is PASS and return completion timestamp.

        Args:
            qc_log_file: The QC status log file

        Returns:
            QC completion timestamp if status is PASS, None otherwise
        """
        try:
            qc_model = FileQCModel.model_validate(qc_log_file.info)
        except ValidationError:
            return False

        # Check if QC status is PASS
        file_status = qc_model.get_file_status()
        return file_status == QC_STATUS_PASS

    def _create_visit_event(
        self,
        *,
        visit_metadata: VisitMetadata,
        project: ProjectAdaptor,
        qc_completion_time: datetime,
    ) -> Optional[VisitEvent]:
        """Create a QC-pass VisitEvent from VisitMetadata.

        Args:
            visit_metadata: The visit metadata
            project: The project
            qc_completion_time: QC completion timestamp

        Returns:
            VisitEvent or None if creation fails
        """
        try:
            # Extract study and datatype from project label
            pipeline_label = PipelineLabel.model_validate(project.label)
        except ValidationError as error:
            log.warning(
                "Project doesn't have expected label. Failed to create visit event: %s",
                error,
            )
            return None

        if pipeline_label.datatype is None:
            log.warning(
                "Pipeline project label should include a datatype: %s", project.label
            )
            return None

        return VisitEvent(
            action=ACTION_PASS_QC,
            study=pipeline_label.study_id,
            pipeline_adcid=project.get_pipeline_adcid(),
            project_label=project.label,
            center_label=project.group,
            gear_name="form-scheduler",
            ptid=visit_metadata.ptid,
            visit_date=visit_metadata.date,
            visit_number=visit_metadata.visitnum,
            datatype=pipeline_label.datatype,
            module=visit_metadata.module,
            packet=visit_metadata.packet,
            timestamp=qc_completion_time,
        )

    def capture_events(self, json_file: FileEntry, project: ProjectAdaptor) -> None:
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
                log.debug("No QC status log found for %s", json_file.name)
                return

            # Check QC status - only proceed if PASS
            if not self._check_qc_status(qc_log_file):
                log.debug("QC status is not PASS for %s", json_file.name)
                return

            # Extract visit metadata
            visit_metadata = self._extract_visit_metadata(json_file, qc_log_file)
            if not visit_metadata:
                log.warning(
                    "Could not extract valid visit metadata for %s", json_file.name
                )
                return

            # Create and log QC-pass event
            visit_event = self._create_visit_event(
                visit_metadata=visit_metadata,
                project=project,
                qc_completion_time=qc_log_file.modified,
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
