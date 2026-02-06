import logging
import re
from typing import Any, Dict, List, Optional

from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from identifiers.model import NACCID_PATTERN
from inputs.csv_reader import CSVVisitor
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_common.error_models import CSVLocation, FileError
from outputs.error_writer import ErrorWriter
from outputs.errors import malformed_file_error, missing_field_error
from outputs.outputs import StringCSVWriter
from pydantic import BaseModel, Field, ValidationError, model_validator

log = logging.getLogger(__name__)


class DataRequest(BaseModel):
    """Data model for a row of a data request file."""

    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)

    @model_validator(mode="before")
    @classmethod
    def fix_case(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k.lower(): v for k, v in value.items()}

        return value


class DataRequestMatch(BaseModel):
    """Data model representing a participant matching data request for
    NACCID."""

    naccid: str
    subject_id: str
    project_label: str


class ModuleDataGatherer:
    """Defines process to gather file.info.form custom info for data
    requests."""

    def __init__(
        self,
        proxy: FlywheelProxy,
        module_name: str,
        info_paths: Optional[list[str]] = None,
    ) -> None:
        self.__proxy = proxy
        self.__module_name = module_name
        self.__writer = StringCSVWriter()
        self.__info_paths = info_paths if info_paths is not None else ["forms.json"]

    @property
    def module_name(self):
        return self.__module_name

    @property
    def content(self):
        return self.__writer.get_content()

    def gather_file_info(self, file: FileEntry) -> None:
        """Writes file info to the writer. Uses the info paths of this object
        to pull the dictionary at file.info.<path> and merges the dictionaries.

        Args:
          file: the file object
        Raises:
          ModuleDataError if path doesn't exist or the value is not a dictionary.
        """
        merged_data = {}
        file = file.reload()
        symbol_table = SymbolTable(file.info)

        for path in self.__info_paths:
            try:
                form_data = symbol_table[path]
            except KeyError as error:
                raise ModuleDataError(
                    f"file.info.{path} not found for {file.file_id}"
                ) from error
            if not isinstance(form_data, dict):
                raise ModuleDataError(
                    f"expected a dictionary at {path}, got {type(form_data)}"
                )

            merged_data.update(form_data)

        self.__writer.write(merged_data)

    def gather_request_data(self, request: DataRequestMatch) -> None:
        """Writes the file custom info to the writer of this object for each
        acquisition of the request subject that is labeled byt the module name.

        Args:
          request: the data request
        """
        files = self.__proxy.get_files(
            f"parent_ref.type=acquisition,parents.subject={request.subject_id},"
            f"acquisition.label={self.__module_name}"
        )
        for file in files:
            try:
                self.gather_file_info(file)
            except ModuleDataError as error:
                log.warning("Failed to load data: %s", str(error))
                continue


class ModuleDataError(Exception):
    """Error when accessing form module data."""


def create_project_matcher(study_id: str, project_names: list[str]) -> re.Pattern[str]:
    """Creates a regex pattern for matching project names.

    Includes the unqualified project names and the names with the study_id as
    a suffix.

    Args:
      study_id: the study-id
      project_names: the list of project names
    Returns:
      the regex pattern to match any of the project names
    """
    temp_project_names = set(project_names)
    temp_project_names.update({f"{name}-{study_id}" for name in project_names})
    return re.compile(f"^{'|'.join(temp_project_names)}$")


class DataRequestVisitor(CSVVisitor):
    """Gathers subject matches for a data request file given as a CSV file
    where each row loads as a DataRequest object."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        error_writer: ErrorWriter,
        project_names: list[str],
        study_id: str,
        gatherers: list[ModuleDataGatherer],
    ) -> None:
        self.__proxy = proxy
        self.__error_writer = error_writer
        self.__expected_studies = {study_id, "adrc"}
        self.__gatherers = gatherers
        self.__project_matcher = create_project_matcher(
            study_id=study_id, project_names=project_names
        )

    @property
    def gatherers(self) -> list[ModuleDataGatherer]:
        return self.__gatherers

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
        """Applies this visitor to the data request row at the line number.

        If the data request validates, matches the subjects with the request
        and project names for this visitor.
        If there are any matches, applies the gatherers of this visitor to
        collect data for the subject.

        Args:
          row: the data request object
          line_num: the line number
        Returns:
          True if the visit had no failure
        """
        try:
            query = DataRequest.model_validate(row)
        except ValidationError as error:
            self.__error_writer.write(malformed_file_error(str(error)))
            return True  # ignore row

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
            for gatherer in self.__gatherers:
                try:
                    gatherer.gather_request_data(request)
                except ModuleDataError as error:
                    log.warning(
                        "Request error for subject %s, module %s: %s",
                        request.subject_id,
                        gatherer.module_name,
                        str(error),
                    )

        return True
