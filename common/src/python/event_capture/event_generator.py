"""EventGenerator for creating VisitEvent objects from extracted log data."""

import logging
from datetime import datetime
from typing import Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from nacc_common.data_identification import DataIdentification
from pipeline.pipeline_label import PipelineLabel
from pydantic import ValidationError

from event_capture.models import QCEventData, SubmitEventData
from event_capture.visit_events import (
    ACTION_NOT_PASS_QC,
    ACTION_PASS_QC,
    ACTION_SUBMIT,
    VisitEvent,
    VisitEventType,
)

log = logging.getLogger(__name__)


def create_visit_event(
    *,
    action: VisitEventType,
    visit_metadata: DataIdentification,
    project: ProjectAdaptor,
    completion_time: datetime,
    gear_name: str,
) -> Optional[VisitEvent]:
    """Create a VisitEvent from visit metadata and project context.

    Parses the project label to extract study and datatype, updates
    visit metadata with the project's pipeline ADCID, and constructs
    the event.

    Args:
        action: The event action (e.g. "submit", "pass-qc", "delete")
        visit_metadata: Identification data for the visit/file
        project: The project adaptor for label and ADCID
        completion_time: Timestamp for the event
        gear_name: Name of the gear that produced the event

    Returns:
        VisitEvent or None if the project label is invalid or missing
        required fields
    """
    try:
        pipeline_label = PipelineLabel.model_validate(project.label)
    except (ValidationError, ValueError) as error:
        log.warning(
            "Project doesn't have expected label. Failed to create visit event: %s",
            error,
        )
        return None

    if pipeline_label.datatype is None:
        log.warning(
            "Pipeline project label should include a datatype: %s",
            project.label,
        )
        return None

    visit_metadata = visit_metadata.with_updates(adcid=project.get_pipeline_adcid())

    try:
        return VisitEvent(
            action=action,
            study=pipeline_label.study_id,
            project_label=project.label,
            center_label=project.group,
            gear_name=gear_name,
            datatype=pipeline_label.datatype,
            data_identification=visit_metadata,
            timestamp=completion_time,
        )
    except ValidationError as error:
        log.warning("Failed to create visit event: %s", error)
        return None


class EventGenerator:
    """Creates VisitEvent objects from extracted log data.

    Caches parsed project metadata (pipeline label and ADCID) to avoid
    re-parsing when creating multiple events for the same project.
    """

    def __init__(self, project: ProjectAdaptor) -> None:
        """Initialize the EventGenerator.

        Args:
            project: The project adaptor for accessing project metadata
        """
        self._project = project
        self._pipeline_adcid: Optional[int] = None
        self._pipeline_label: Optional[PipelineLabel] = None

        # Cache pipeline ADCID
        try:
            self._pipeline_adcid = self._project.get_pipeline_adcid()
        except ProjectError as error:
            log.warning("Failed to get pipeline ADCID: %s", error)

        # Cache pipeline label
        try:
            self._pipeline_label = PipelineLabel.model_validate(self._project.label)
        except (ValidationError, ValueError) as error:
            log.warning("Project doesn't have expected label: %s", error)

    def _create_event(
        self,
        *,
        action: VisitEventType,
        visit_metadata: DataIdentification,
        completion_time: datetime,
        gear_name: str,
    ) -> Optional[VisitEvent]:
        """Create a VisitEvent using cached project metadata.

        Args:
            action: The event action (e.g. "submit", "pass-qc")
            visit_metadata: Identification data for the visit/file
            completion_time: Timestamp for the event
            gear_name: Name of the gear that produced the event

        Returns:
            VisitEvent or None if cached metadata is incomplete
        """
        if not self._pipeline_label:
            return None

        if self._pipeline_label.datatype is None:
            log.warning(
                "Pipeline project label should include a datatype: %s",
                self._project.label,
            )
            return None

        visit_metadata = visit_metadata.with_updates(adcid=self._pipeline_adcid)

        try:
            return VisitEvent(
                action=action,
                study=self._pipeline_label.study_id,
                project_label=self._project.label,
                center_label=self._project.group,
                gear_name=gear_name,
                datatype=self._pipeline_label.datatype,
                data_identification=visit_metadata,
                timestamp=completion_time,
            )
        except ValidationError as error:
            log.warning("Failed to create visit event: %s", error)
            return None

    def create_submission_event(
        self, event_data: SubmitEventData
    ) -> Optional[VisitEvent]:
        """Create a submission event from extracted log data.

        Args:
            event_data: The extracted event data from a log file

        Returns:
            VisitEvent object for submission, or None if creation fails
        """
        return self._create_event(
            action=ACTION_SUBMIT,
            visit_metadata=event_data.visit_metadata,
            completion_time=event_data.submission_timestamp,
            gear_name="transactional-event-scraper",
        )

    def create_qc_event(self, event_data: QCEventData) -> Optional[VisitEvent]:
        """Create a event from extracted log data.

        Only creates an event if a completion timestamp exists.

        Args:
            event_data: The extracted event data from a log file

        Returns:
            VisitEvent object for pass-qc or not-pass-qc, or None if
            creation fails or not applicable
        """
        action = (
            ACTION_PASS_QC if event_data.qc_status == "PASS" else ACTION_NOT_PASS_QC
        )

        if not event_data.qc_completion_timestamp:
            log.warning("Cannot create qc event: missing QC completion timestamp")
            return None

        return self._create_event(
            action=action,
            visit_metadata=event_data.visit_metadata,
            completion_time=event_data.qc_completion_timestamp,
            gear_name="transactional-event-scraper",
        )
