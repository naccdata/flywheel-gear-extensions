"""Defines Gather Submission Status Gear."""

import logging
from csv import DictWriter
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional, TextIO, get_args

from centers.center_group import CenterGroup
from centers.nacc_group import NACCGroup
from dataview.dataview import ColumnModel, make_builder
from flywheel.models.data_view import DataView
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import (
    CSVLocation,
    ErrorWriter,
    FileError,
    malformed_file_error,
    missing_field_error,
)
from pydantic import BaseModel, ValidationError, field_serializer, field_validator

log = logging.getLogger(__name__)

Modality = Literal["UDS", "FTLD", "LBD"]
Study = Literal["adrc", "dvcid", "leads"]
QCStatus = Literal["pass", "fail"]


def create_status_view(modules: List[Modality]) -> DataView:
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
            ColumnModel(data_key="subject.label", label="participant_id"),
            ColumnModel(data_key="file.modified", label="modified_date"),
        ],
        container="acquisition",
        filter_str=f'acquisition.label=|[{",".join(modules)}]',
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

    filename: str
    file_id: str
    module: str
    naccid: str
    modified_date: date
    qc_status: Optional[QCStatus] = None

    @field_validator("modified_date", mode="before")
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


class StatusFilter:
    """Process for handling submission status of files for particular
    subjects."""

    def __init__(self, proxy: FlywheelProxy, writer: DictWriter) -> None:
        self.__proxy = proxy
        self.__writer = writer

    def gather_status(
        self, subject: SubjectAdaptor, modalities: List[Modality]
    ) -> None:
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
        view = create_status_view(modalities)
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
            qc_object = file.get("info", {}).get("qc", {})
            for gear_name in qc_object:
                qc_state = qc_object.get(gear_name).get("validation", {}).get("state")
                if qc_state is not None:
                    if qc_state.lower() == "fail":
                        status.qc_status = "fail"
                        continue
                    status.qc_status = "pass" if qc_state.lower() == "pass" else None

            self.__writer.writerow(status.model_dump())


class StatusRequest(BaseModel):
    """Data model for a row of the status request file."""

    adcid: int
    naccid: str
    study: Study
    modalities: List[Modality]

    @field_serializer("modalities")
    def serialize_list_as_string(self, modalities: List[Modality]) -> str:
        return ",".join(modalities)

    @field_validator("modalities", mode="before")
    @classmethod
    def modality_list(cls, value: Any) -> List[Modality]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            raise ValueError(f"expecting modalities to be a string, got {type(value)}")

        modality_list = value.split(",")
        mismatches = [name for name in modality_list if name not in get_args(Modality)]
        if mismatches:
            raise ValueError(f"found unexpected modalities: {', '.join(mismatches)}")

        return modality_list  # type: ignore


class SubmissionStatusVisitor(CSVVisitor):
    """Determines form status for each participant."""

    def __init__(
        self,
        *,
        admin_group: NACCGroup,
        project_names: List[str],
        status_filter: StatusFilter,
        error_writer: ErrorWriter,
    ) -> None:
        self.__admin_group = admin_group
        self.__project_names = project_names
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

    def __get_projects(self, center: CenterGroup, study: Study) -> List[ProjectAdaptor]:
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
                pattern = f"{project}-{study}" if study != "adrc" else project
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

        center = self.__get_center(status_query.adcid)
        if not center:
            self.__error_writer.write(
                FileError(
                    error_code="no-center",
                    error_type="error",
                    location=CSVLocation(line=line_num, column_name="adcid"),
                    message=f"value {status_query.adcid} is not a valid ADCID",
                )
            )
            return False

        projects = self.__get_projects(center=center, study=status_query.study)
        if not projects:
            self.__error_writer.write(
                FileError(
                    error_code="no-projects",
                    error_type="error",
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
                self.__filter.gather_status(
                    subject=subject, modalities=status_query.modalities
                )
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
    proxy: FlywheelProxy,
    error_writer: ErrorWriter,
):
    """Runs the Gather Submission Status process.

    Args:
        proxy: the proxy for the Flywheel instance
    """
    writer = DictWriter(output_file, fieldnames=list(StatusModel.model_fields.keys()))
    visitor = SubmissionStatusVisitor(
        admin_group=admin_group,
        project_names=project_names,
        status_filter=StatusFilter(proxy=proxy, writer=writer),
        error_writer=error_writer,
    )

    return read_csv(input_file=input_file, error_writer=error_writer, visitor=visitor)
