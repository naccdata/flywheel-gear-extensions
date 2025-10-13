"""Defines status request type and request clustering visitor."""

import re
from typing import Any, Dict, List

from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from inputs.csv_reader import CSVVisitor
from outputs.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error, missing_field_error
from pydantic import BaseModel, ValidationError


class StatusRequest(BaseModel):
    """Data model for a row of the status request file."""

    adcid: int
    ptid: str


class StatusRequestClusteringVisitor(CSVVisitor):
    """CSV visitor to load and cluster submission status requests by ADCID."""

    def __init__(
        self,
        proxy: FlywheelProxy,
        study_id: str,
        project_names: List[str],
        error_writer: ErrorWriter,
    ) -> None:
        self.__proxy = proxy
        self.__error_writer = error_writer
        self.__project_names = list(project_names)
        self.__project_names.extend({f"{name}-{study_id}" for name in project_names})
        self.__project_matcher = re.compile(f"^{'|'.join(self.__project_names)}$")
        self.pipeline_map: dict[int, list[ProjectAdaptor]] = {}
        self.request_map: Dict[int, List[StatusRequest]] = {}

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

    def __get_projects(self, adcid: int) -> list[ProjectAdaptor]:
        """Returns the projects with pipeline ADCID and matching project names
        in this visitor.

        Args:
          adcid: the pipeline ADCID
        Returns:
          the projects with the pipeline ADCID and matching project names
        """
        result = self.pipeline_map.get(adcid)
        if result is not None:
            return result

        pipeline_projects = self.__proxy.get_pipeline(adcid)
        projects = [
            project
            for project in pipeline_projects
            if self.__project_matcher.match(project.label)
        ]
        self.pipeline_map[adcid] = projects

        return projects

    def __add_request(self, status_query: StatusRequest) -> None:
        """Add a status request to the request map of this visitor.

        Maps pipeline ADCID to request.

        Args:
          status_query: the request
        """
        request_list = self.request_map.get(status_query.adcid, [])
        request_list.append(status_query)
        self.request_map[status_query.adcid] = request_list

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Processes a row of the status request file.

        Args:
          row: the dictionary for the row
          line_num: the line number of the row
        """
        try:
            query = StatusRequest.model_validate(row)
        except ValidationError as error:
            self.__error_writer.write(malformed_file_error(str(error)))
            return False

        projects = self.__get_projects(query.adcid)
        if not projects:
            self.__error_writer.write(
                FileError(
                    error_code="no-projects",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="adcid"),
                    message=(
                        f"ADCID {query.adcid} has no matching projects "
                        f"with names {self.__project_names}"
                    ),
                )
            )
            return True

        self.__add_request(status_query=query)

        return True
