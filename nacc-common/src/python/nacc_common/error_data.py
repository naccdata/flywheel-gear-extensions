import logging
import re
from typing import Any, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.models.project import Project
from pydantic import ValidationError

from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import FileQCModel
from nacc_common.qc_report import (
    QC_FILENAME_PATTERN,
    ListReportWriter,
    ProjectReportVisitor,
    WriterTableVisitor,
    extract_visit_keys,
)
from nacc_common.visit_submission_error import (
    ErrorReportModel,
    error_report_visitor_builder,
)
from nacc_common.visit_submission_status import (
    StatusReportModel,
    status_report_visitor_builder,
)

log = logging.getLogger(__name__)

ModuleName = str

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


def _find_submission(project: Project, identifier: str) -> Optional[FileEntry]:
    """Resolves an opaque submission identifier to the underlying FileEntry.

    Currently the identifier maps to a QC status log filename, but this is an
    implementation detail hidden behind this helper.

    Args:
      project: the flywheel project object
      identifier: the opaque submission identifier
    Returns:
      the FileEntry if found, None otherwise
    """
    for file in project.files:
        if file.name == identifier:
            file = file.reload()
            return file
    return None


def _should_include_file(
    filename: str,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> bool:
    """Determines whether a QC log file should be included based on filters.

    Matches the filename against QC_FILENAME_PATTERN and applies optional PTID
    and module filters.

    Args:
      filename: the filename to check
      modules: optional set of module names to filter by (compared upper-cased)
      ptids: optional set of PTIDs to filter by
    Returns:
      True if the file matches the pattern and passes all filters
    """
    match = re.match(QC_FILENAME_PATTERN, filename)
    if not match:
        return False

    ptid = match.group(1)
    if ptids is not None and ptid not in ptids:
        return False

    module = match.group(3).upper()
    return modules is None or module in modules


def get_status_data(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Returns a list of dictionaries containing QC status data for files in
    the project.

    Args:
      project: the project
      modules: optional set of module names to filter by
      ptids: optional set of PTIDs to filter by
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
        ptid_set=ptids,
        file_visitor_factory=status_report_visitor_builder,
        table_visitor=WriterTableVisitor(ListReportWriter(result)),
    )
    project_visitor.visit_project(project)

    return result


def get_error_data(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Creates a list of dictionaries, each corresponding to an error in a file
    in the project.

    Args:
      project: the flywheel project object
      modules: optional set of module names to filter by
      ptids: optional set of PTIDs to filter by
    Returns:
      a list contain error info objects for files in the project
    Raises:
      ReportError if the project doesn't have an associated ADCID
    """
    project = project.reload()
    adcid = get_pipeline_adcid(project)
    if adcid is None:
        raise ReportError(f"Project {project.label} has no associated ADCID")

    result: list[dict[str, Any]] = []
    list_writer = ListReportWriter(result)
    project_visitor = ProjectReportVisitor(
        adcid=adcid,
        modules=modules,
        ptid_set=ptids,
        file_visitor_factory=error_report_visitor_builder,
        table_visitor=WriterTableVisitor(list_writer),
    )
    project_visitor.visit_project(project)

    return result


def get_submission_qc_summary(
    project: Project, identifier: str
) -> Optional[dict[str, Any]]:
    """Returns a plain-dict QC summary for a specific submission.

    Resolves the identifier to a submission, builds a FileQCModel, and returns
    a dict with the overall status and per-stage status/error counts.

    Args:
      project: the flywheel project object
      identifier: the opaque submission identifier
    Returns:
      a dict with "identifier", "overall_status", and "stages", or None if the
      submission is not found, has no QC data, or QC data is malformed
    """
    file_entry = _find_submission(project, identifier)
    if file_entry is None:
        return None

    try:
        qc_model = FileQCModel.create(file_entry)
    except ValidationError:
        return None

    if not qc_model.qc:
        return None

    stages: dict[str, dict[str, Any]] = {}
    for gear_name, gear_model in qc_model.qc.items():
        stages[gear_name] = {
            "status": gear_model.get_status(),
            "error_count": len(gear_model.get_errors()),
        }

    return {
        "identifier": identifier,
        "overall_status": qc_model.get_file_status(),
        "stages": stages,
    }


def get_submission_errors(project: Project, identifier: str) -> list[dict[str, Any]]:
    """Returns a flat list of error dicts for a specific submission.

    Resolves the identifier to a submission, builds a FileQCModel, and
    collects all errors across all stages. Each error dict includes all
    FileError fields (serialized with aliases) plus a "stage" key.

    Args:
      project: the flywheel project object
      identifier: the opaque submission identifier
    Returns:
      a list of error dicts, or an empty list if the submission is not
      found, has no errors, or QC data is malformed
    """
    file_entry = _find_submission(project, identifier)
    if file_entry is None:
        return []

    try:
        qc_model = FileQCModel.create(file_entry)
    except ValidationError:
        return []

    errors: list[dict[str, Any]] = []
    for gear_name, gear_model in qc_model.qc.items():
        for file_error in gear_model.get_errors():
            error_dict = file_error.model_dump(by_alias=True)
            error_dict["stage"] = gear_name
            errors.append(error_dict)

    return errors


def get_submission_visit_metadata(
    project: Project, identifier: str
) -> Optional[dict[str, Any]]:
    """Returns visit metadata for a specific submission as a plain dict.

    Resolves the identifier to a submission and extracts visit metadata
    using DataIdentification.from_visit_info().

    Args:
      project: the flywheel project object
      identifier: the opaque submission identifier
    Returns:
      a dict with visit metadata fields (participant identifiers, date,
      visit number, module/modality, packet), or None if the submission
      is not found or has no visit metadata
    """
    file_entry = _find_submission(project, identifier)
    if file_entry is None:
        return None

    data_id = DataIdentification.from_visit_info(file_entry)
    if data_id is None:
        return None

    return data_id.model_dump()


def list_submissions(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Returns a list of submission summary dicts for QC log files in the
    project, with optional filtering by module and/or PTID.

    For each matching file, extracts visit keys from the filename and
    attempts to determine the overall QC status. If the QC data is
    missing or malformed, overall_status is set to None.

    Args:
      project: the flywheel project object
      modules: optional set of module names to filter by (compared upper-cased)
      ptids: optional set of PTIDs to filter by
    Returns:
      a list of dicts, each with "identifier", "ptid", "date", "module",
      and "overall_status"
    """
    result: list[dict[str, Any]] = []

    for file in project.files:
        if not _should_include_file(file.name, modules=modules, ptids=ptids):
            continue

        visit_keys = extract_visit_keys(file)

        try:
            qc_model = FileQCModel.create(file)
            overall_status: Optional[str] = qc_model.get_file_status()
        except ValidationError:
            overall_status = None

        result.append(
            {
                "identifier": file.name,
                "ptid": visit_keys.ptid,
                "date": visit_keys.date,
                "module": visit_keys.module,
                "overall_status": overall_status,
            }
        )

    return result
