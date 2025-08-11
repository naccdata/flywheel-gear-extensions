"""Defines Gather Submission Status Gear."""

import logging
from csv import DictWriter
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, TextIO

from centers.center_group import CenterGroup
from centers.nacc_group import NACCGroup
from dataview.dataview import ColumnModel, make_builder
from flywheel.models.data_view import DataView
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.error_models import (
    CSVLocation,
    FileError,
    FileQCModel,
    FileQCVisitor,
    QCStatus,
    ValidationModel,
)
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    malformed_file_error,
    missing_field_error,
)
from pydantic import BaseModel, ValidationError, field_validator

log = logging.getLogger(__name__)

ModuleName = Literal["UDS", "FTLD", "LBD"]


def create_status_view(modules: List[ModuleName]) -> DataView:
    """Creates a dataview for participant submission status for files matching
    the given modalities.

    Args:
      modalities: the modalities
    Returns:
      the data view using the modalities as filters
    """
    builder = make_builder(
        label="participant-status",
        description="Capture status of participant submissions",
        columns=[
            ColumnModel(data_key="file.name", label="filename"),
            ColumnModel(data_key="file.file_id", label="file_id"),
            ColumnModel(data_key="acquisition.label", label="module"),
            ColumnModel(data_key="subject.label", label="naccid"),
            ColumnModel(data_key="file.modified", label="modified_date"),
            ColumnModel(data_key="file.info.forms.json.visitdate", label="visit_date"),
        ],
        container="acquisition",
        filter_str=f"acquisition.label=|[{','.join(modules)}]",
        missing_data_strategy="none",
    )
    builder.file_filter(value=r"^.*\.json", regex=True)
    builder.file_container("acquisition")
    return builder.build()


class StatusModel(BaseModel):
    """Data model corresponding to the data view created by create_status_view.

    Note: `qc_status` field is not part of the dataview and must
    be set separately.
    """

    naccid: str
    module: str
    visit_date: date
    filename: str
    file_id: str
    modified_date: date
    qc_status: Optional[QCStatus] = None

    @field_validator("modified_date", "visit_date", mode="before")
    def datetime_to_date(cls, value: str) -> date:
        """Converts datetime string to date.

        Args:
          value: the datetime string
        Returns:
          the date for the datetime string
        """
        return datetime.fromisoformat(value).date()


class StatusResponseModel(BaseModel):
    """Response model for dataview, which is a list of StatusModel objects."""

    data: List[StatusModel]

    @field_validator("data", mode="before")
    def trim_data(cls, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove any rows that are completely empty, which can happen if the
        filename pattern does not match.

        Args:
            data: List of retrieved rows from the builder
        Returns:
            Trimmed data
        """
        return [row for row in data if any(x is not None for x in row.values())]


class StatusError(Exception):
    """Exception for status filter."""


class StatusVisitor(FileQCVisitor):
    def __init__(self, status: StatusModel, writer: DictWriter) -> None:
        self.__status = status
        self.__writer = writer

    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        self.__status.qc_status = validation_model.state
        self.__writer.writerow(self.__status.model_dump())


class StatusFilter:
    """Process for handling submission status of files for particular
    subjects."""

    def __init__(self, proxy: FlywheelProxy, writer: DictWriter) -> None:
        self.__proxy = proxy
        self.__writer = writer

    def gather_status(self, subject: SubjectAdaptor, modules: List[ModuleName]) -> None:
        """Gathers submission status details for acquisitions with the
        modalities associated with the subject.

        Uses a dataview to find all acquisitions matching the modalities,
        checks the QC status of each file, and finally writes the status to the
        Dict writer.

        Args:
          subject: the subject
          modalities: the file modalities
        Raises:
          StatusError if there is an error validating the dataview
        """
        view = create_status_view(modules)
        response = self.__proxy.read_view_data(view, subject.id)
        response_data = response.read()
        try:
            response_model = StatusResponseModel.model_validate_json(response_data)
        except ValidationError as error:
            raise StatusError(
                f"error in file status object for {subject.label}: {error}"
            ) from error

        for status in response_model.data:
            file = self.__proxy.get_file(status.file_id)
            try:
                qc_info = FileQCModel.model_validate(file.info)
            except ValidationError as error:
                log.error(f"Unexpected QC metadata for file {file.name}: {error}")
                continue
            qc_info.apply(StatusVisitor(status=status, writer=self.__writer))


class StatusRequest(BaseModel):
    """Data model for a row of the status request file."""

    adcid: int
    naccid: str
    study: str


class SubmissionStatusVisitor(CSVVisitor):
    """Determines form status for each participant."""

    def __init__(
        self,
        *,
        admin_group: NACCGroup,
        project_names: List[str],
        study_id: str,
        modules: List[ModuleName],
        status_filter: StatusFilter,
        error_writer: ErrorWriter,
    ) -> None:
        self.__admin_group = admin_group
        self.__project_names = project_names
        self.__expected_studies = {study_id, "adrc"}
        self.__modules = modules
        self.__filter = status_filter
        self.__error_writer = error_writer
        self.__center_map: Dict[int, CenterGroup] = {}
        self.__project_map: Dict[str, List[ProjectAdaptor]] = {}

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
        projects = self.__project_map.get(center.label, [])
        if not projects:
            for project in self.__project_names:
                pattern = f"{project}-{study_id}" if study_id != "adrc" else project
                matching_projects = center.get_matching_projects(pattern)
                if matching_projects:
                    projects += matching_projects
            self.__project_map[center.label] = projects

        return projects

    def visit_header(self, header: List[str]) -> bool:
        """Checks that the header has ADCID and NACCID keys, and adds to this
        visitor.

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

        for project in projects:
            subject = project.find_subject(status_query.naccid)
            if not subject:
                continue

            try:
                self.__filter.gather_status(subject=subject, modules=self.__modules)
            except StatusError as error:
                log.error("error loading status: %s", str(error))
                continue

        return True


def run(
    *,
    input_file: TextIO,
    output_file: TextIO,
    admin_group: NACCGroup,
    project_names: List[str],
    modules: List[ModuleName],
    study_id: str,
    proxy: FlywheelProxy,
    error_writer: ErrorWriter,
):
    """Runs the Gather Submission Status process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    writer = DictWriter(output_file, fieldnames=list(StatusModel.model_fields))
    visitor = SubmissionStatusVisitor(
        admin_group=admin_group,
        project_names=project_names,
        modules=modules,
        study_id=study_id,
        status_filter=StatusFilter(proxy=proxy, writer=writer),
        error_writer=error_writer,
    )

    writer.writeheader()
    return read_csv(input_file=input_file, error_writer=error_writer, visitor=visitor)
