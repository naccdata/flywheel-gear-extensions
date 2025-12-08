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
    FileQCModel,
    ValidationModel,
    VisitKeys,
)
from nacc_common.module_types import ModuleName
from nacc_common.qc_report import (
    ErrorReportVisitor,
    ErrorTransformer,
    ProjectReportVisitor,
    QCReportBaseModel,
    QCTransformerError,
    ReportTableVisitor,
)
from nacc_common.visit_submission_error import ErrorReportModel, error_transformer
from pydantic import BaseModel, ConfigDict

from nacc_common.visit_submission_status import StatusReportModel

log = logging.getLogger(__name__)


class FirstErrorVisitor(ErrorReportVisitor):
    """Finds the FIRST FileError in QC metadata.

    Unlike ErrorReportVisitor which finds all errors, this visitor stops
    after finding the first error to get timestamp and gear info.
    """

    def __init__(self, transformer: ErrorTransformer) -> None:
        super().__init__(transformer)

    def visit_file_model(self, file_model: FileQCModel) -> None:
        """Visit file model and stop after finding first error."""
        if self.table:
            return
        super().visit_file_model(file_model)

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Visit validation model and check for errors."""
        if self.table:
            return

        state = validation_model.state
        if state is not None and state.lower() == "pass":
            return

        # Found a non-pass state, get first error if available
        if validation_model.data:
            validation_model.data[0].apply(self)


class VisitKey(BaseModel):
    """Composite key for uniquely identifying a visit."""

    model_config = ConfigDict(frozen=True)

    ptid: str
    visit_date: str
    module: str

class VisitStatusReportModel(StatusReportModel):
    timestamp: Optional[str] = None
    visit_number: Optional[str] = None

def event_status_transformer(
    gear_name: str, visit: VisitKeys, validation_model: ValidationModel
) -> VisitStatusReportModel:
    """Transformer for creating visit status report objects from a file QC validation model.

    Args:
      gear_name: the gear name corresponding to the validation model
      visit: the visit attributes for the file
      validation_model: the validation model

    Raises:
      QCTransformerError if the visit ptid, module and date are not set
    """
    if (
        visit.adcid is None
        or visit.ptid is None
        or visit.module is None
        or visit.date is None
    ):
        raise QCTransformerError("Cannot generate status incomplete visit details")

    if visit.module not in get_args(ModuleName):
        raise QCTransformerError(f"Unexpected module name: {visit.module}")

    return VisitStatusReportModel(
        adcid=visit.adcid,
        ptid=visit.ptid,
        module=visit.module, # pyright: ignore[reportArgumentType]
        visitdate=visit.date,
        stage=gear_name,
        status=validation_model.state
    )

def create_visit_event(
    status_model: VisitStatusReportModel,
    project: ProjectAdaptor,
    datatype: DatatypeNameType,
    packet: Optional[str] = None,
) -> Optional[VisitEvent]:
    if status_model.timestamp is None:
        log.warning(
            "Expecting timestamp for not-pass-qc event for %s", status_model.ptid
        )
        return
    timestamp = datetime.strptime(status_model.timestamp, "%Y-%m-%d %H:%M:%S")

    if not status_model.stage:
        log.warning("No gear name known for not-pass-qc event for %s", status_model.ptid)
        return None
    if not status_model.visit_number:
        log.warning(
            "No visit number known for not-pass-qc event for %s", status_model.ptid
        )
        return None

    return VisitEvent(
        action="not-pass-qc",
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



class EventTableVisitor(ReportTableVisitor):
    """Visitor for error report to create VisitEvent objects. Handles qc pass
    and non-pass events.

    Submit events are handled by the submit-logger gear
    """

    def __init__(
        self,
        event_logger: VisitEventLogger,
        project: ProjectAdaptor,
        datatype: DatatypeNameType,
        packet: Optional[str] = None,
    ) -> None:
        self.__event_logger = event_logger
        self.__project = project
        self.__datatype = datatype
        self.__packet = packet

    def visit_row(self, row: QCReportBaseModel) -> None:
        if not isinstance(row, VisitStatusReportModel):
            log.warning("Type of error model is incorrect for event logging")
            return
        visit_event = create_visit_event(
            status_model=row,
            project=self.__project,
            datatype=self.__datatype,  # type: ignore
            packet=self.__packet,
        )
        if visit_event is None:
            return None

        self.__event_logger.log_event(visit_event)


def create_modified_filter(timestamp: datetime) -> Callable[[FileEntry], bool]:
    def after_timestamp(file: FileEntry) -> bool:
        return file.modified >= timestamp

    return after_timestamp


class EventAccumulator:
    def __init__(
        self,
        pipeline: Pipeline,
        event_logger: VisitEventLogger,
        datatype: DatatypeNameType = "form",
    ) -> None:
        self.__pipeline = pipeline
        self.__event_logger = event_logger
        self.__datatype = datatype

    def log_events(self, file: FileEntry, project: ProjectAdaptor) -> None:

        # TODO: want a mix of error report and status report
        # could potentially do error report and then do status report
        # but that would involve crawling the qc object twice
        error_visitor = ProjectReportVisitor(
            adcid=project.get_pipeline_adcid(),
            modules=set(self.__pipeline.modules) if self.__pipeline.modules else None,  # type: ignore
            file_visitor=FirstErrorVisitor(event_status_transformer),
            table_visitor=EventTableVisitor(
                self.__event_logger, project, self.__datatype  # type: ignore
            ),
            file_filter=create_modified_filter(file.created),
        )

        error_visitor.visit_project(project)
