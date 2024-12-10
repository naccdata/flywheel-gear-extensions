"""Defines csv_center_splitter."""
import logging
from typing import Any, Dict, List, Optional, TextIO

from flywheel import FileSpec
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    missing_field_error,
    unexpected_value_error,
)
from outputs.outputs import write_csv_to_stream
from projects.project_mapper import build_project_map

log = logging.getLogger(__name__)


class CSVVisitorCenterSplitter(CSVVisitor):
    """Class for visiting each row in CSV."""

    def __init__(self,
                 adcid_key: str,
                 error_writer: ListErrorWriter,
                 allow_merged_cells: bool = False):
        """Initializer."""
        self.__adcid_key: str = adcid_key
        self.__error_writer: ListErrorWriter = error_writer
        self.__split_data: Dict[int, List[str]] = {}
        self.__headers: List[str] = []

        self.__allow_merged_cells = allow_merged_cells
        self.__prev_adcid: Optional[int] = None

    @property
    def adcid_key(self):
        """The header ADCID key."""
        return self.__adcid_key

    @property
    def split_data(self):
        """The data split by the header key."""
        return self.__split_data

    @property
    def centers(self):
        """Return the centers split on."""
        return list(self.__split_data.keys())

    @property
    def headers(self):
        """Return the data headers."""
        return self.__headers

    @property
    def error_writer(self):
        """Return the error writer."""
        return self.__error_writer

    def visit_header(self, header: List[str]) -> bool:
        """Adds the header and verifies that the header key is in it.

        Args:
          header: list of header names
        Returns:
          True if the header has the header key, False otherwise
        """
        self.__headers = header
        result = self.adcid_key in header
        if not result:
            error = missing_field_error(self.adcid_key)
            self.__error_writer.write(error)

        return result

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for a row (per DictReader).

        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        try:
            # handle the merged rows case; if ADCID key is missing, assume
            # same as previous row
            # TODO: might want to do a clean up of empty rows? Or just assume
            # a clean CSV?
            raw_adcid = row[self.adcid_key]

            if not raw_adcid:
                if self.__allow_merged_cells:
                    raw_adcid = self.__prev_adcid
                else:
                    message = f"Row {line_num} was invalid: Missing ADCID value"
                    error = empty_field_error(field=self.adcid_key,
                                              line=line_num,
                                              message=message)
                    self.__error_writer.write(error)
                    return False

            adcid = int(raw_adcid)
            self.__prev_adcid = adcid
        except ValueError as e:
            message = f"Row {line_num} was invalid: ADCID value must be an int: {e}"
            error = unexpected_value_error(field=self.adcid_key,
                                           value=raw_adcid,
                                           expected="integer value",
                                           line=line_num,
                                           message=message)
            self.__error_writer.write(error)
            return False

        if adcid not in self.split_data:
            self.split_data[adcid] = []

        self.split_data[adcid].append(row)
        return True


def run(*,
        proxy: FlywheelProxy,
        input_file: TextIO,
        input_filename: str,
        error_writer: ListErrorWriter,
        adcid_key: str,
        target_project: str,
        staging_project_id: Optional[str] = None,
        allow_merged_cells: bool = False,
        delimiter: str = ','):
    """Runs the CSV Center Splitter. Splits an input CSV by ADCID and uploads
    to each center's target project.

    Args:
        proxy: the proxy for the Flywheel instance
        input_file: The input CSV TextIO stream to split on
        input_filename: The name of the input CSV, used to build the filename
            for split files
        error_writer: The ListErrorWriter to write errors to
        adcid_key: The name of the header column the ADCID is listed under
        target_project: The FW target project name to write results to for
                        each ADCID

        staging_project_id: Project ID to stage results to; will override
                            target_project if specified
        allow_merged_cells: Whether or not to allow merged cells
        delimiter: The CSV's delimiter; defaults to ','
    """
    # split CSV by ADCID key
    visitor = CSVVisitorCenterSplitter(adcid_key, error_writer,
                                       allow_merged_cells)
    success = read_csv(input_file=input_file,
                       error_writer=error_writer,
                       visitor=visitor,
                       delimiters=delimiter)

    if not success:
        log.error(
            "The following errors were found while reading input CSV file, " +
            "will not split data.")
        for x in error_writer.errors():
            log.error(x['message'])
        return

    project_map: Dict[str, Any] = {}
    if staging_project_id:
        # if writing results to a staging project, manually build a project map
        # that maps all to the specified project ID
        project = proxy.get_project_by_id(staging_project_id)
        project_map = {f'adcid-{adcid}': project for adcid in visitor.centers}
    else:
        # else build project map from ADCID to corresponding
        # FW project for upload
        project_map = build_project_map(proxy=proxy,
                                        destination_label=target_project,
                                        center_filter=visitor.centers)

    if not project_map:
        raise ValueError(f"No {target_project} projects found")

    # make sure all expected projects are there before upload
    missing_projects = []
    for adcid in visitor.split_data:
        if f'adcid-{adcid}' not in project_map:
            missing_projects.append(adcid)

    if missing_projects:
        raise ValueError(
            f"Missing {target_project} projects for the following " +
            f"ADCIDs: {missing_projects}")

    log.info(
        f"Writing split results for the following ADCIDs: {visitor.centers}")

    # write results to each center's project
    for adcid, data in visitor.split_data.items():
        project = project_map[f'adcid-{adcid}']
        filename = f'{adcid}_{input_filename}'

        if staging_project_id:
            log.info(
                f"Uploading {filename} to staging project {staging_project_id} "
                + f"for ADCID {adcid}")
        else:
            log.info(
                f"Uploading {filename} for project {target_project} ADCID "
                + f"{adcid} with project ID {project.id}")

        contents = write_csv_to_stream(headers=visitor.headers,
                                       data=data,
                                       filename=filename).getvalue()
        file_spec = FileSpec(name=filename,
                             contents=contents,
                             content_type="text/csv",
                             size=len(contents))

        if proxy.dry_run:
            log.info(f"DRY RUN: Would have uplaoded {filename}")
        else:
            project.upload_file(file_spec)
            log.info(f"Successfully uploaded {filename}")
