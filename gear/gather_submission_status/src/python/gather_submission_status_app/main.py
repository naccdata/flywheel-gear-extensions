"""Defines Gather Submission Status Gear."""

import logging
from csv import DictWriter
from typing import Any, Dict, List, Literal, Optional, TextIO

from centers.center_group import CenterGroup
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.error_models import (
    CSVLocation,
    FileError,
)
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    malformed_file_error,
    missing_field_error,
)
from outputs.qc_report import FileQCReportVisitor, ProjectReportVisitor
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

ModuleName = Literal["UDS", "FTLD", "LBD"]


class StatusError(Exception):
    """Exception for status filter."""


class StatusRequest(BaseModel):
    """Data model for a row of the status request file."""

    adcid: int
    ptid: str
    study: str


class RequestClusteringVisitor(CSVVisitor):
    def __init__(
        self,
        admin_group: NACCGroup,
        study_id: str,
        project_names: List[str],
        error_writer: ErrorWriter,
    ) -> None:
        self.__admin_group = admin_group
        self.__error_writer = error_writer
        self.__expected_studies = {study_id, "adrc"}
        self.__center_map: Dict[int, CenterGroup] = {}
        self.__project_names = project_names
        self.project_map: Dict[str, List[ProjectAdaptor]] = {}
        self.request_map: Dict[str, List[StatusRequest]] = {}

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has ADCID, PTID and study keys.

        Args:
          header: list of header names
        Returns:
          True if the header has expected column names. False, otherwise.
        """
        missing_headers = set(StatusRequest.model_fields).difference(header)
        if missing_headers:
            self.__error_writer.write(missing_field_error(missing_headers))
            return False

        return True

    def __get_center(self, adcid: int) -> Optional[CenterGroup]:
        """Gets the center group for the adcid if it exists.

        memoizes center groups

        Args:
          adcid: the ADCID
        Returns:
          the CenterGroup for the ADCID if one exists. None, otherwise
        """
        center = self.__center_map.get(adcid)
        if not center:
            center = self.__admin_group.get_center(adcid)
            if center:
                self.__center_map[adcid] = center
        return center

    def __get_projects(
        self, center: CenterGroup, study_id: str
    ) -> List[ProjectAdaptor]:
        """Gets the projects matching the prefix in the center group.

        Args:
          center: the group
          prefix: the project name prefix
        Returns:
          the list of projects in the group matching the prefix
        """
        projects: List[ProjectAdaptor] = self.project_map.get(center.label, [])
        if not projects:
            for project in self.__project_names:
                pattern = project if study_id == "adrc" else f"{project}-{study_id}"
                matching_projects = center.get_matching_projects(pattern)
                if matching_projects:
                    project_list = self.project_map.get(center.label, [])
                    project_list.extend(matching_projects)
                    self.project_map[center.label] = project_list

        return projects

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Processes a row of the status request file.

        Args:
          row: the dictionary for the row
          line_num: the line number of the row
        """
        try:
            status_query = StatusRequest.model_validate(row)
        except ValidationError as error:
            self.__error_writer.write(malformed_file_error(str(error)))
            return False

        if status_query.study not in self.__expected_studies:
            self.__error_writer.write(
                FileError(
                    error_code="unexpected-study",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="study"),
                    message=(
                        f"expected one of {', '.join(self.__expected_studies)},"
                        f" got {status_query.study}"
                    ),
                )
            )
            return True  # ignore row

        center = self.__get_center(status_query.adcid)
        if not center:
            self.__error_writer.write(
                FileError(
                    error_code="no-center",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="adcid"),
                    message=f"value {status_query.adcid} is not a valid ADCID",
                )
            )
            return False

        projects = self.__get_projects(center=center, study_id=status_query.study)
        if not projects:
            self.__error_writer.write(
                FileError(
                    error_code="no-projects",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="adcid"),
                    message=(
                        f"center {status_query.adcid} has no matching projects "
                        f"for {status_query.study} and names {self.__project_names}"
                    ),
                )
            )
            return False

        request_list = self.request_map.get(center.label, [])
        request_list.append(status_query)
        self.request_map[center.label] = request_list

        return True


def run(
    *,
    input_file: TextIO,
    output_file: TextIO,
    admin_group: NACCGroup,
    project_names: List[str],
    modules: List[ModuleName],
    study_id: str,
    file_visitor: FileQCReportVisitor,
    report_fieldnames: List[str],
    error_writer: ErrorWriter,
):
    """Runs the Gather Submission Status process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    clustering = RequestClusteringVisitor(
        admin_group=admin_group,
        study_id=study_id,
        project_names=project_names,
        error_writer=error_writer,
    )
    ok_status = read_csv(
        input_file=input_file, error_writer=error_writer, visitor=clustering
    )
    if not ok_status:
        return False

    writer = DictWriter(output_file, fieldnames=list(report_fieldnames))
    writer.writeheader()

    project_map = clustering.project_map
    for center_label, project_list in project_map.items():
        request_list = clustering.request_map.get(center_label)
        if not request_list:
            log.warning("No participants found for center %s", center_label)
            continue
        ptid_set = {request.ptid for request in request_list}

        for project in project_list:
            project_visitor = ProjectReportVisitor(
                modules=set(modules),
                ptid_set=ptid_set,
                file_visitor=file_visitor,
                writer=writer,
            )
            project_visitor.visit_project(project)

    return True
