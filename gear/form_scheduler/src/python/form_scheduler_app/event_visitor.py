import logging
from datetime import datetime
from typing import Callable

from configs.ingest_configs import Pipeline
from event_logging.event_logging import VisitEventLogger
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import (
    FileQCModel,
    ValidationModel,
)
from nacc_common.qc_report import (
    ErrorReportVisitor,
    ErrorTransformer,
    ProjectReportVisitor,
    QCReportBaseModel,
    ReportTableVisitor,
)
from nacc_common.visit_submission_error import ErrorReportModel, error_transformer
from pydantic import BaseModel, ConfigDict

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


class EventTableVisitor(ReportTableVisitor):
    def __init__(self, event_logger: VisitEventLogger) -> None:
        self.__event_logger = event_logger
        self.__logged_submits: set[VisitKey] = set()

    def visit_row(self, row: QCReportBaseModel) -> None:
        if not isinstance(row, ErrorReportModel):
            log.warning("Type of error model is incorrect for event logging")
            return
        # how do we know that the row corresponds to the file?

        # 1. create a submit if possible
        # 2. create a no-pass if possible


def create_modified_filter(timestamp: datetime) -> Callable[[FileEntry], bool]:
    def after_timestamp(file: FileEntry) -> bool:
        return file.modified >= timestamp

    return after_timestamp


class EventAccumulator:
    def __init__(
        self,
        pipeline: Pipeline,
        event_logger: VisitEventLogger,
    ) -> None:
        self.__pipeline = pipeline
        self.__event_logger = event_logger

    def log_events(self, file: FileEntry, project: ProjectAdaptor) -> None:
        error_visitor = ProjectReportVisitor(
            adcid=project.get_pipeline_adcid(),
            modules=set(self.__pipeline.modules) if self.__pipeline.modules else None,  # type: ignore
            file_visitor=FirstErrorVisitor(error_transformer),
            table_visitor=EventTableVisitor(self.__event_logger),
            file_filter=create_modified_filter(file.created),
        )

        error_visitor.visit_project(project)
