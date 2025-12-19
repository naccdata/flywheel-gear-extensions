"""Simplified event accumulator for QC-pass events only."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from error_logging.error_logger import ErrorLogTemplate
from event_logging.event_logger import VisitEventLogger
from event_logging.visit_events import ACTION_PASS_QC, VisitEvent
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.types import DatatypeNameType
from nacc_common.error_models import (
    QC_STATUS_PASS,
    FileQCModel,
    VisitMetadata,
)
from pipeline.pipeline_label import PipelineLabel
from pydantic import ValidationError

log = logging.getLogger(__name__)


class VisitMetadataExtractor:
    """Utility for extracting VisitMetadata from QC status or JSON files."""

    @staticmethod
    def from_qc_status_custom_info(
        custom_info: Dict[str, Any],
    ) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from QC status custom info.

        Args:
            custom_info: Custom info from QC status log file

        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        if not custom_info:
            return None

        visit_data = custom_info.get("visit")
        if not visit_data:
            return None

        try:
            return VisitMetadata.model_validate(visit_data)
        except ValidationError:
            return None

    @staticmethod
    def from_json_file_metadata(json_file: FileEntry) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from JSON file forms metadata.

        Args:
            json_file: JSON file with forms metadata

        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        if not json_file or not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        try:
            # Create mapping for field name differences
            mapped_data = {**forms_json, "date": forms_json.get("visitdate")}
            return VisitMetadata.model_validate(mapped_data)
        except ValidationError:
            return None

    @staticmethod
    def is_valid_for_event(visit_metadata: VisitMetadata) -> bool:
        """Check if VisitMetadata has required fields for VisitEvent
        creation."""
        if not visit_metadata:
            return False

        return bool(
            visit_metadata.ptid and visit_metadata.date and visit_metadata.module
        )


class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""

    def __init__(
        self, event_logger: VisitEventLogger, datatype: DatatypeNameType = "form"
    ) -> None:
        """Initialize the simplified EventAccumulator.

        Args:
            event_logger: Logger for visit events
            datatype: Type of data being processed (default: "form")
        """
        self.__event_logger = event_logger
        self.__datatype = datatype
        self.__error_log_template = ErrorLogTemplate()

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
        if not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        module = forms_json.get("module")
        if not module:
            return None

        # Use ErrorLogTemplate to generate expected QC status log filename
        qc_log_name = self.__error_log_template.instantiate(
            record=forms_json, module=module
        )
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

    def _check_qc_status(self, qc_log_file: FileEntry) -> Optional[datetime]:
        """Check if QC status is PASS and return completion timestamp.

        Args:
            qc_log_file: The QC status log file

        Returns:
            QC completion timestamp if status is PASS, None otherwise
        """
        try:
            qc_model = FileQCModel.model_validate(qc_log_file.info)
        except ValidationError:
            return None

        # Check if QC status is PASS
        file_status = qc_model.get_file_status()
        if file_status != QC_STATUS_PASS:
            return None

        # Return the file modification timestamp as QC completion time
        return qc_log_file.modified

    def _create_visit_event(
        self,
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
            # Extract study from project label
            pipeline_label = PipelineLabel.model_validate(project.label)
            study = pipeline_label.study_id

            # Get visit event fields from VisitMetadata with field name mapping
            event_fields = visit_metadata.model_dump()
            # Map field names for VisitEvent
            if "date" in event_fields:
                event_fields["visit_date"] = event_fields.pop("date")
            if "visitnum" in event_fields:
                event_fields["visit_number"] = event_fields.pop("visitnum")

            return VisitEvent(
                action=ACTION_PASS_QC,
                study=study,
                pipeline_adcid=project.get_pipeline_adcid(),
                project_label=project.label,
                center_label=project.group,
                gear_name="form-scheduler",
                ptid=event_fields["ptid"],
                visit_date=event_fields["visit_date"],
                visit_number=event_fields.get("visit_number"),
                datatype=self.__datatype,
                module=event_fields["module"],
                packet=event_fields.get("packet"),
                timestamp=qc_completion_time,
            )
        except (ValidationError, KeyError) as e:
            log.warning(f"Failed to create visit event: {e}")
            return None

    def log_events(self, json_file: FileEntry, project: ProjectAdaptor) -> None:
        """Log QC-pass events for a JSON file if it passes QC validation.

        Args:
            json_file: JSON file from finalization queue
            project: The project containing QC status logs
        """
        try:
            # Find corresponding QC status log
            qc_log_file = self.find_qc_status_for_json_file(json_file, project)
            if not qc_log_file:
                log.debug(f"No QC status log found for {json_file.name}")
                return

            # Check QC status - only proceed if PASS
            qc_completion_time = self._check_qc_status(qc_log_file)
            if not qc_completion_time:
                log.debug(f"QC status is not PASS for {json_file.name}")
                return

            # Extract visit metadata
            visit_metadata = self._extract_visit_metadata(json_file, qc_log_file)
            if not visit_metadata:
                log.warning(
                    f"Could not extract valid visit metadata for {json_file.name}"
                )
                return

            # Create and log QC-pass event
            visit_event = self._create_visit_event(
                visit_metadata, project, qc_completion_time
            )
            if visit_event:
                self.__event_logger.log_event(visit_event)
                log.info(f"Logged QC-pass event for {json_file.name}")
            else:
                log.warning(f"Failed to create visit event for {json_file.name}")

        except Exception as e:
            # Log error but don't fail pipeline processing
            log.error(f"Error logging events for {json_file.name}: {e}", exc_info=True)
