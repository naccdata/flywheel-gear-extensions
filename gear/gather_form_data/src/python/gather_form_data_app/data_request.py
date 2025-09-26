import re
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from identifiers.model import NACCID_PATTERN
from inputs.csv_reader import CSVVisitor
from outputs.error_writer import ErrorWriter
from outputs.errors import missing_field_error


class DataRequest(BaseModel):
    """Data model for a row of a data request file."""
    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)
    study: str

class RequestClusteringVisitor(CSVVisitor):

    def __init__(self, admin_group: NACCGroup, error_writer: ErrorWriter, project_names: list[str]) -> None:
        self.__admin_group = admin_group
        self.__error_writer = error_writer
        self.__pipeline_map: dict[int, dict[str, ProjectAdaptor]]
        self.__project_names = project_names

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has ADCID, PTID and study keys.

        Args:
          header: list of header names
        Returns:
          True if the header has expected column names. False, otherwise.
        """
        missing_headers = set(DataRequest.model_fields).difference(header)
        if missing_headers:
            self.__error_writer.write(missing_field_error(missing_headers))
            return False

        return True

    def __load_pipeline(self, adcid: int) -> None:
        if adcid in self.__pipeline_map:
            return

        project_map: dict[str, ProjectAdaptor] = {}
        projects = self.__admin_group.get_pipeline(adcid)

        pattern = f"^{'|'.join(self.__project_names)}$"
        matcher = re.compile(pattern)
        project_map = {project.label: project for project in projects if matcher.match(project.label)}
        if not project_map:
            return

        self.__pipeline_map[adcid] = project_map

    def __get_projects(self, adcid: int) -> list[ProjectAdaptor]:
        self.__load_pipeline(adcid)

        return []

    
    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        return super().visit_row(row, line_num)