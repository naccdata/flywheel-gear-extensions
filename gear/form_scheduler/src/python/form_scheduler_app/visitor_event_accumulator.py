"""Defines manager for accumulation of events from QC log files."""

import logging
from datetime import datetime
from typing import Callable, Optional, get_args

from configs.ingest_configs import Pipeline
from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.types import DatatypeNameType
from nacc_common.error_models import (
    FileError,
    FileQCModel,
    ValidationModel,
    VisitKeys,
)
from nacc_common.module_types import ModuleName
from nacc_common.qc_report import (
    ErrorTransformer,
    FileQCReportVisitor,
    ProjectReportVisitor,
    QCReportBaseModel,
    QCTransformerError,
    ReportTableVisitor,
    ValidationTransformer,
)
from nacc_common.visit_submission_error import ErrorReportModel, error_transformer
from nacc_common.visit_submission_status import StatusReportModel
from pipeline.pipeline_label import PipelineLabel
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)


class VisitStatusReportModel(StatusReportModel):
    timestamp: Optional[str] = None
    visit_number: Optional[str] = None


class EventReportVisitor(FileQCReportVisitor):
    """Defines a QC reporting visitor for gathering event report objects for
    file.

    Finds the first FileError or last passing validation in QC metadata.
    """

    def __init__(
        self,
        file: FileEntry,
        adcid: int,
        *,
        error_transformer: ErrorTransformer,
        validation_transformer: ValidationTransformer,
    ) -> None:
        super().__init__(file, adcid)
        self.__error_transformer = error_transformer
        self.__validation_transformer = validation_transformer
        self.__file_modified_timestamp = file.modified
        self.__error: QCReportBaseModel | None = None
        self.__validation: QCReportBaseModel | None = None

    def add(self, item: QCReportBaseModel) -> None:
        if isinstance(item, VisitStatusReportModel):
            self.__validation = item
        if isinstance(item, ErrorReportModel):
            self.__error = item

    @property
    def table(self) -> list[QCReportBaseModel]:
        if self.__error is not None:
            return [self.__error]

        if self.__validation:
            return [self.__validation]

        return []

    def clear(self) -> None:
        self.__error = None
        self.__validation = None

    def visit_file_model(self, file_model: FileQCModel) -> None:
        """Override to check for empty qc object before processing."""
        # Stop processing if qc object is empty
        if not file_model.qc:
            return

        # Call parent implementation for normal processing
        super().visit_file_model(file_model)

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Defines a visit for a validation model.

        Finds the first FileError, or the last pass ValidationModel.

        Applies the validation transformer to the validation model if the state
        is pass.

        Args:
          validation_model: the model to visit
        """
        if self.__error is not None:
            return
        if self.visit_details is None:
            return
        if self.gear_name is None:
            return
        if validation_model.state is None:
            return

        if validation_model.state.lower() == "pass":
            # Call the validation transformer with the file timestamp
            result = event_status_transformer(
                self.gear_name,
                self.visit_details,
                validation_model,
                self.__file_modified_timestamp,
            )
            self.add(result)
            return

        for error_model in validation_model.data:
            error_model.apply(self)
            if self.__error:
                return

    def visit_file_error(self, file_error: FileError) -> None:
        """Defines a visit for a file error.

        Applies the error transformer
        """
        if self.__error is not None:
            return
        if self.gear_name is None:
            return
        if self.visit_details is None:
            return

        self.add(
            self.__error_transformer(self.gear_name, self.visit_details, file_error)
        )


class VisitKey(BaseModel):
    """Composite key for uniquely identifying a visit."""

    model_config = ConfigDict(frozen=True)

    ptid: str
    visit_date: str
    module: str


def event_status_transformer(
    gear_name: str,
    visit: VisitKeys,
    validation_model: ValidationModel,
    file_modified_timestamp: Optional[datetime] = None,
) -> VisitStatusReportModel:
    """Transformer for creating visit status report objects from a file QC
    validation model.

    Args:
      gear_name: the gear name corresponding to the validation model
      visit: the visit attributes for the file
      validation_model: the validation model
      file_modified_timestamp: the QC status file modification timestamp to use for pass events

    Raises:
      QCTransformerError if the visit ptid, module and date are not set
    """
    if (
        visit.adcid is None
        or visit.ptid is None
        or visit.module is None
        or visit.date is None
    ):
        raise QCTransformerError("Cannot generate status: incomplete visit details")

    if visit.module not in get_args(ModuleName):
        raise QCTransformerError(f"Unexpected module name: {visit.module}")

    # For pass events, use the QC status file modification timestamp
    timestamp_str = None
    if (
        file_modified_timestamp
        and validation_model.state
        and validation_model.state.lower() == "pass"
    ):
        timestamp_str = file_modified_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    return VisitStatusReportModel(
        adcid=visit.adcid,
        ptid=visit.ptid,
        module=visit.module,  # pyright: ignore[reportArgumentType]
        visitdate=visit.date,
        stage=gear_name,
        status=validation_model.state,
        timestamp=timestamp_str,
        visit_number=visit.visitnum,  # Visit number is optional
    )


def create_visit_event_from_error(
    *,
    error_model: ErrorReportModel,
    study: str,
    project: ProjectAdaptor,
    datatype: DatatypeNameType,
    packet: Optional[str] = None,
) -> VisitEvent | None:
    """Creates a VisitEvent from an ErrorReportModel.

    Errors unrelated to a participant or visit are skipped.

    Args:
      error_model: the error report model
      study: the name of the study
      project: the pipeline project
      datatype: the submitted datatype
      packet: the form packet if the datatype is form
    Returns:
      the VisitEvent if all expected values are given. None, otherwise.
    """
    if error_model.ptid is None:
        log.warning("skipping non-visit error: no ptid")
        return None
    if error_model.date is None:
        log.warning("skipping non-visit error: no date")
        return None
    if error_model.visitnum is None:
        log.warning("skipping non-visit error: no visit number")
        return None
    if error_model.timestamp is None:
        log.warning("skipping error with no timestamp")
        return None
    timestamp = datetime.strptime(error_model.timestamp, "%Y-%m-%d %H:%M:%S")

    return VisitEvent(
        action="not-pass-qc",
        study=study,
        pipeline_adcid=error_model.adcid,
        project_label=project.label,
        center_label=project.group,
        gear_name=error_model.stage,
        ptid=error_model.ptid,
        visit_date=error_model.date,
        visit_number=error_model.visitnum,
        datatype=datatype,
        module=error_model.module,
        packet=packet,
        timestamp=timestamp,
    )


def create_visit_event_from_status(
    *,
    status_model: VisitStatusReportModel,
    study: str,
    project: ProjectAdaptor,
    datatype: DatatypeNameType,
    packet: Optional[str] = None,
):
    """Creates a VisitEvent from an VisitStatusReportModel.

    Expects the status to be "PASS".

    Args:
      status: the status report model
      study: the name of the study
      project: the pipeline project
      datatype: the submitted datatype
      packet: the form packet if the datatype is form
    Returns:
      the VisitEvent if all expected values are given. None, otherwise.
    """
    if status_model.status != "PASS":
        log.warning("skipping non-pass validation event")
        return None
    if status_model.timestamp is None:
        log.warning("Expecting timestamp for pass event for %s", status_model.ptid)
        return None
    if not status_model.stage:
        log.warning("No gear name known for pass event for %s", status_model.ptid)
        return None
    # Visit number is optional - it may not be available for all pass events

    timestamp = datetime.strptime(status_model.timestamp, "%Y-%m-%d %H:%M:%S")
    return VisitEvent(
        action="pass-qc",
        study=study,
        pipeline_adcid=status_model.adcid,
        project_label=project.label,
        center_label=project.group,
        gear_name=status_model.stage,
        ptid=status_model.ptid,
        visit_date=status_model.visitdate,
        visit_number=status_model.visit_number,
        datatype=datatype,
        module=status_model.module,
        packet=packet,
        timestamp=timestamp,
    )


def create_visit_event(
    *,
    visit_model: QCReportBaseModel,
    study: str,
    project: ProjectAdaptor,
    datatype: DatatypeNameType,
    packet: Optional[str] = None,
) -> Optional[VisitEvent]:
    """Creates a VisitEvent from an VisitStatusReportModel or ErrorReportModel.

    Expects the status to be "PASS".

    Args:
      status: the status report model
      study: the name of the study
      project: the pipeline project
      datatype: the submitted datatype
      packet: the form packet if the datatype is form
    Returns:
      the VisitEvent build for the report model.
      None, if the report model is the wrong type, or a event cannot be created
    """
    if isinstance(visit_model, ErrorReportModel):
        return create_visit_event_from_error(
            error_model=visit_model,
            study=study,
            project=project,
            datatype=datatype,
            packet=packet,
        )
    if isinstance(visit_model, VisitStatusReportModel):
        return create_visit_event_from_status(
            status_model=visit_model,
            study=study,
            project=project,
            datatype=datatype,
            packet=packet,
        )
    return None


class EventTableVisitor(ReportTableVisitor):
    """Visitor for error report to create VisitEvent objects. Handles qc pass
    and non-pass events.

    Submit events are handled by the submit-logger gear
    """

    def __init__(
        self,
        *,
        event_logger: VisitEventLogger,
        study: str,
        project: ProjectAdaptor,
        datatype: DatatypeNameType,
        packet: Optional[str] = None,
    ) -> None:
        self.__event_logger = event_logger
        self.__study = study
        self.__project = project
        self.__datatype = datatype
        self.__packet = packet

    def visit_row(self, row: QCReportBaseModel) -> None:
        if not isinstance(row, (VisitStatusReportModel, ErrorReportModel)):
            log.warning("Type of error model is incorrect for event logging")
            return
        visit_event = create_visit_event(
            visit_model=row,
            study=self.__study,
            project=self.__project,
            datatype=self.__datatype,  # type: ignore
            packet=self.__packet,
        )
        if visit_event is None:
            return None

        self.__event_logger.log_event(visit_event)


def create_modified_filter(timestamp: datetime) -> Callable[[FileEntry], bool]:
    """Creates file predicate for files modified after the timestamp.

    Args:
      timestamp: the timestamp to use in the predicate
    Returns:
      a predicate testing whether a file is modified after the timestamp
    """

    def after_timestamp(file: FileEntry) -> bool:
        """Returns true if the file is modified after the timestamp.

        Args:
          file: the file to check
        Returns:
          True if the file is modified after the timestamp. False, otherwise.
        """
        return file.modified >= timestamp

    return after_timestamp


class EventAccumulator:
    """Accumulates visit events for files with QC-status reports."""

    def __init__(
        self,
        *,
        pipeline: Pipeline,
        event_logger: VisitEventLogger,
        datatype: DatatypeNameType = "form",
    ) -> None:
        self.__pipeline = pipeline
        self.__event_logger = event_logger
        self.__datatype = datatype

    def log_events(self, file: FileEntry, project: ProjectAdaptor) -> None:
        """Logs the events for QC-status reports modified after the file
        creation.

        Extracts the study identifier from the project label.

        Args:
          file: the submitted file
          project: the pipeline project with qc-status files
        """
        # Extract study from project label
        pipeline_label = PipelineLabel.model_validate(project.label)
        study = pipeline_label.study_id

        error_visitor = ProjectReportVisitor(
            adcid=project.get_pipeline_adcid(),
            modules=set(self.__pipeline.modules) if self.__pipeline.modules else None,  # type: ignore
            file_visitor_factory=lambda file, adcid: EventReportVisitor(
                file=file,
                adcid=adcid,
                error_transformer=error_transformer,
                validation_transformer=event_status_transformer,
            ),
            table_visitor=EventTableVisitor(
                event_logger=self.__event_logger,
                study=study,
                project=project,
                datatype=self.__datatype,  # type: ignore
            ),
            file_filter=create_modified_filter(file.created),
        )

        error_visitor.visit_project(project)
