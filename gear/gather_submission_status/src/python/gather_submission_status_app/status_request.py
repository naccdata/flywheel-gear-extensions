"""Defines status request type and request clustering visitor."""

from typing import Any, Dict, List, Optional

from centers.center_group import CenterGroup
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor
from nacc_common.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error, missing_field_error
from pydantic import BaseModel, ValidationError


class StatusRequest(BaseModel):
    """Data model for a row of the status request file."""

    adcid: int
    ptid: str
    study: str


class RequestClusteringVisitor(CSVVisitor):
    """CSV visitor to load and cluster submission status requests by center."""

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
        projects: List[ProjectAdaptor] = self.project_map.get(center.id, [])
        if not projects:
            for project_name in self.__project_names:
                pattern = (
                    rf"^{project_name}$"
                    if study_id == "adrc"
                    else rf"^{project_name}-{study_id}$"
                )
                projects.extend(center.get_matching_projects(pattern=pattern))
            self.project_map[center.id] = projects

        return projects

    def __add_request(self, center: CenterGroup, status_query: StatusRequest) -> None:
        """Add a status request to the request map of this visitor.

        Maps center ID to request.

        Args:
          center: the center group
          status_query: the request
        """
        request_list = self.request_map.get(center.id, [])
        request_list.append(status_query)
        self.request_map[center.id] = request_list

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

        self.__add_request(center=center, status_query=status_query)

        return True
