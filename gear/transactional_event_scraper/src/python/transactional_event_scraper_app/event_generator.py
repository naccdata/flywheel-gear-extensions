"""EventGenerator for creating VisitEvent objects from extracted log data."""

import logging
from typing import Optional

from event_capture.visit_events import ACTION_PASS_QC, ACTION_SUBMIT, VisitEvent
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from pipeline.pipeline_label import PipelineLabel
from pydantic import ValidationError

from transactional_event_scraper_app.models import EventData

log = logging.getLogger(__name__)


class EventGenerator:
    """Creates VisitEvent objects from extracted log data."""

    def __init__(self, project: ProjectAdaptor) -> None:
        """Initialize the EventGenerator.

        Args:
            project: The project adaptor for accessing project metadata
        """
        self._project = project
        self._pipeline_label: Optional[PipelineLabel] = None
        self._pipeline_adcid: Optional[int] = None

        # Parse project label and extract metadata
        try:
            # PipelineLabel uses a wrap validator that accepts strings
            self._pipeline_label = PipelineLabel.model_validate(self._project.label)
        except (ValidationError, ValueError) as error:
            log.warning(
                "Failed to parse project label %s: %s", self._project.label, error
            )

        # Get pipeline ADCID
        try:
            self._pipeline_adcid = self._project.get_pipeline_adcid()
        except ProjectError as error:
            log.warning("Failed to get pipeline ADCID: %s", error)

    def create_submission_event(self, event_data: EventData) -> Optional[VisitEvent]:
        """Create a submission event from extracted log data.

        Args:
            event_data: The extracted event data from a log file

        Returns:
            VisitEvent object for submission, or None if creation fails
        """
        if not self._pipeline_label or not self._pipeline_adcid:
            log.warning(
                "Cannot create submission event: missing project metadata "
                "(label=%s, adcid=%s)",
                self._pipeline_label,
                self._pipeline_adcid,
            )
            return None

        if self._pipeline_label.datatype is None:
            log.warning(
                "Pipeline project label should include a datatype: %s",
                self._project.label,
            )
            return None

        try:
            return VisitEvent(
                action=ACTION_SUBMIT,
                study=self._pipeline_label.study_id,
                pipeline_adcid=self._pipeline_adcid,
                project_label=self._project.label,
                center_label=self._project.group,
                gear_name="transactional-event-scraper",
                ptid=event_data.visit_metadata.ptid,
                visit_date=event_data.visit_metadata.date,
                visit_number=event_data.visit_metadata.visitnum,
                datatype=self._pipeline_label.datatype,
                module=event_data.visit_metadata.module,
                packet=event_data.visit_metadata.packet,
                timestamp=event_data.submission_timestamp,
            )
        except ValidationError as error:
            log.warning("Failed to create submission event: %s", error)
            return None

    def create_pass_qc_event(self, event_data: EventData) -> Optional[VisitEvent]:
        """Create a pass-qc event from extracted log data.

        Only creates an event if the QC status is PASS and a completion
        timestamp exists.

        Args:
            event_data: The extracted event data from a log file

        Returns:
            VisitEvent object for pass-qc, or None if creation fails or not
            applicable
        """
        # Only create pass-qc events for PASS status
        if event_data.qc_status != "PASS":
            return None

        if not event_data.qc_completion_timestamp:
            log.warning("Cannot create pass-qc event: missing QC completion timestamp")
            return None

        if not self._pipeline_label or not self._pipeline_adcid:
            log.warning(
                "Cannot create pass-qc event: missing project metadata "
                "(label=%s, adcid=%s)",
                self._pipeline_label,
                self._pipeline_adcid,
            )
            return None

        if self._pipeline_label.datatype is None:
            log.warning(
                "Pipeline project label should include a datatype: %s",
                self._project.label,
            )
            return None

        try:
            return VisitEvent(
                action=ACTION_PASS_QC,
                study=self._pipeline_label.study_id,
                pipeline_adcid=self._pipeline_adcid,
                project_label=self._project.label,
                center_label=self._project.group,
                gear_name="transactional-event-scraper",
                ptid=event_data.visit_metadata.ptid,
                visit_date=event_data.visit_metadata.date,
                visit_number=event_data.visit_metadata.visitnum,
                datatype=self._pipeline_label.datatype,
                module=event_data.visit_metadata.module,
                packet=event_data.visit_metadata.packet,
                timestamp=event_data.qc_completion_timestamp,
            )
        except ValidationError as error:
            log.warning("Failed to create pass-qc event: %s", error)
            return None
