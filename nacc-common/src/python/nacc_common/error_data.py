from typing import Any, Optional

from flywheel.models.project import Project

from nacc_common.module_types import ModuleName
from nacc_common.qc_report import (
    ErrorReportVisitor,
    ListReportWriter,
    ProjectReportVisitor,
    StatusReportVisitor,
    WriterTableVisitor,
)
from nacc_common.visit_submission_error import ErrorReportModel, error_transformer
from nacc_common.visit_submission_status import StatusReportModel, status_transformer

ERROR_HEADER_NAMES: list[str] = ErrorReportModel.serialized_fieldnames()
STATUS_HEADER_NAMES: list[str] = list(StatusReportModel.model_fields.keys())


class ReportError(Exception):
    pass


def get_pipeline_adcid(project: Project) -> Optional[int]:
    """Returns the pipeline ADCID for the project.

    Args:
      project: the flywheel project object
    Returns:
      the value of pipeline ADCID in project. None if none set.
    """
    adcid = project.info.get("pipeline_adcid")
    if adcid is None:
        return None

    return int(adcid)


def get_status_data(
    project: Project, modules: Optional[set[ModuleName]] = None
) -> list[dict[str, Any]]:
    """Returns a list of dictionaries containing QC status data for files in
    the project.

    Args:
      project: the project
    Returns:
      a list containing status info objects for files in the project
    Raises:
      ReportError if the project doesn't have an associated ADCID
    """
    project = project.reload()
    adcid = get_pipeline_adcid(project)
    if adcid is None:
        raise ReportError(f"Project {project.label} has no associated ADCID")

    result: list[dict[str, Any]] = []

    project_visitor = ProjectReportVisitor(
        adcid=adcid,
        modules=modules,
        file_visitor=StatusReportVisitor(status_transformer),
        table_visitor=WriterTableVisitor(ListReportWriter(result)),
    )
    project_visitor.visit_project(project)

    return result


def get_error_data(
    project: Project, modules: Optional[set[ModuleName]] = None
) -> list[dict[str, Any]]:
    """Creates a list of dictionaries, each corresponding to an error in a file
    in the project.

    Args:
      project: the flywheel project object
    Returns:
      a list contain error info objects for files in the project
    Raises:
      ReportError if the project doesn't have an associated ADCID
    """
    project = project.reload()
    adcid = get_pipeline_adcid(project)
    if adcid is None:
        raise ReportError(f"Project {project.label} has no associated ADCID")

    file_visitor = ErrorReportVisitor(error_transformer)
    result: list[dict[str, Any]] = []
    list_writer = ListReportWriter(result)
    project_visitor = ProjectReportVisitor(
        adcid=adcid,
        modules=modules,
        file_visitor=file_visitor,
        table_visitor=WriterTableVisitor(list_writer),
    )
    project_visitor.visit_project(project)

    return result
