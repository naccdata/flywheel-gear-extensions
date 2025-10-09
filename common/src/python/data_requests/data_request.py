import re
from typing import Any, Dict, List

from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from identifiers.model import NACCID_PATTERN
from inputs.csv_reader import CSVVisitor
from keys.types import ModuleName
from outputs.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error, missing_field_error
from pydantic import BaseModel, Field, ValidationError

from outputs.outputs import StringCSVWriter


class DataRequest(BaseModel):
    """Data model for a row of a data request file."""

    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)


class DataRequestMatch(BaseModel):
    """Data model representing a participant matching data request for
    NACCID."""

    naccid: str
    subject_id: str
    project_label: str


class DataRequestVisitor(CSVVisitor):
    """Gathers subject matches for a data request file given as a CSV file
    where each row loads as a DataRequest object."""

    def __init__(
        self,
        proxy: FlywheelProxy,
        error_writer: ErrorWriter,
        project_names: list[str],
        study_id: str,
    ) -> None:
        self.__proxy = proxy
        self.__error_writer = error_writer
        self.__expected_studies = {study_id, "adrc"}
        temp_project_names = set(project_names)
        temp_project_names.update({f"{name}-{study_id}" for name in project_names})
        self.__project_matcher = re.compile(f"^{'|'.join(temp_project_names)}$")

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

    def __get_matches(self, request: DataRequest) -> list[DataRequestMatch]:
        """Returns list of subject IDs matching the NACCID in the request that
        have projects matching the study and name constraints.

        Args:
          request: the data request
        Returns:
          a list of subject IDs
        """
        result = []
        subjects = self.__proxy.get_subject_by_label(request.naccid)
        for subject in subjects:
            parent_project = self.__proxy.get_container_by_id(subject.parents.project)
            if self.__project_matcher.match(parent_project.label):
                result.append(
                    DataRequestMatch(
                        naccid=request.naccid,
                        subject_id=subject.id,
                        project_label=parent_project.label,
                    )
                )

        return result

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        try:
            query = DataRequest.model_validate(row)
        except ValidationError as error:
            self.__error_writer.write(malformed_file_error(str(error)))

        matching_requests = self.__get_matches(request=query)
        if not matching_requests:
            self.__error_writer.write(
                FileError(
                    error_code="no-participant",  # pyright: ignore[reportCallIssue]
                    error_type="error",  # pyright: ignore[reportCallIssue]
                    location=CSVLocation(line=line_num, column_name="naccid"),
                    message=(
                        f"no participant {query.naccid} with data for "
                        f"{','.join(self.__expected_studies)}"
                    ),
                )
            )
            return True  # ignore row

        for request in matching_requests:
            files = __gather_files
        return True

class ModuleDataGatherer:

    def __init__(self, proxy: FlywheelProxy, module_name: ModuleName) -> None:
        self.__proxy = proxy
        self.__module_name = module_name
        self.__writer = StringCSVWriter()

    def visit_file(self, file: FileEntry) -> None:
        file = file.reload()
        form_data = file.info.get("forms")
        if not form_data:
            raise ModuleDataError(f"Expected file.info.forms for {file.file_id}")
        json_data = form_data.get("json")
        if not json_data:
            raise ModuleDataError(f"Expecting file.info.forms.json for {file.file_id}")

        self.__writer.write(json_data)

    def gather_request_data(self, request: DataRequestMatch) -> None:
        files = self.__proxy.get_files(
            f"parent_ref.type=acquisition,parents.subject={request.subject_id},"
            f"acquisition.label={self.__module_name}"
        )
        for file in files:
            self.visit_file(file)

class ModuleDataError(Exception):
    """Error when accessing form module data"""
