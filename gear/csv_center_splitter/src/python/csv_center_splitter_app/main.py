"""Defines csv_center_splitter."""

import logging
from typing import Any, Dict, List, Optional, Set, TextIO

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import CSVVisitor, read_csv
from jobs.job_poll import JobPoll
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    empty_field_error,
    missing_field_error,
)
from outputs.outputs import write_csv_to_stream
from projects.project_mapper import generate_project_map

log = logging.getLogger(__name__)


class CSVVisitorCenterSplitter(CSVVisitor):
    """Class for visiting each row in CSV."""

    def __init__(
        self, *, adcid_key: str, include: Set[str], error_writer: ListErrorWriter
    ):
        """Initializer."""
        self.__adcid_key: str = adcid_key
        self.__include = include
        self.__error_writer: ListErrorWriter = error_writer
        self.__split_data: Dict[str, List[Dict[str, Any]]] = {}
        self.__headers: List[str] = []

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

        TODO: Should we clean up/ignore empty rows? Or just assume
              a clean CSV? Particularly in the merged cells case.

        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        adcid = row[self.adcid_key]
        if not adcid:
            message = f"Row {line_num} was invalid: Missing ADCID value"
            error = empty_field_error(
                field=self.adcid_key, line=line_num, message=message
            )
            self.__error_writer.write(error)
            return False

        if adcid not in self.__include:
            return True  # skip center not explicitly included

        if adcid not in self.split_data:
            self.split_data[adcid] = []

        self.split_data[adcid].append(row)
        return True


def run(
    *,
    proxy: FlywheelProxy,
    input_file: TextIO,
    input_filename: str,
    error_writer: ListErrorWriter,
    adcid_key: str,
    batch_size: int,
    target_project: Optional[str] = None,
    staging_project_id: Optional[str] = None,
    include: Optional[Set[str]] = None,
    downstream_gears: Optional[List[str]] = None,
    delimiter: str = ",",
):
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
        batch_size: Number of centers to put in each batch for scheduling

        staging_project_id: Project ID to stage results to; will override
                            target_project if specified
        include: Centers to include
        downstream_gears: Gears to wait on before processing the
            next batch when scheduling
        delimiter: The CSV's delimiter; defaults to ','
    """
    # split CSV by ADCID key
    visitor = CSVVisitorCenterSplitter(
        adcid_key=adcid_key,
        include=include if include else set(),
        error_writer=error_writer,
    )
    success = read_csv(
        input_file=input_file,
        error_writer=error_writer,
        visitor=visitor,
        delimiter=delimiter,
    )

    if not success:
        log.error(
            "The following errors were found while reading input CSV file, "
            + "will not split data."
        )
        for error in error_writer.errors():
            log.error(error.message)
        return

    # filter to centers that were actually found
    centers = [adcid for adcid in visitor.split_data]
    project_map = generate_project_map(
        proxy=proxy,
        centers=centers,
        target_project=target_project,
        staging_project_id=staging_project_id,
    )

    if not project_map:
        raise GearExecutionError(f"No {target_project} projects found")

    # make sure all expected projects are there before upload
    missing_projects = [
        adcid for adcid in centers if not project_map.get(f"adcid-{adcid}", None)
    ]
    if missing_projects:
        raise GearExecutionError(
            f"Missing {target_project} projects for the following "
            + f"ADCIDs: {missing_projects}"
        )

    batched_centers = [
        centers[i : i + batch_size] for i in range(0, len(centers), batch_size)
    ]

    log.info(
        "Writing split results for the following ADCIDs "
        + f"in {len(batched_centers)} batches: {batched_centers}"
    )

    # write results to each center's project
    for i, batch in enumerate(batched_centers, start=1):
        log.info(f"Running batch {i} of {len(batched_centers)}")
        project_ids_list = []

        for adcid in batch:
            data = visitor.split_data[adcid]
            project = project_map[f"adcid-{adcid}"]
            filename = f"{adcid}_{input_filename}"

            log.info(
                f"Uploading {filename} for project {project.label} "  # type: ignore
                + f"ADCID {adcid} with project ID {project.id}"
            )  # type: ignore

            contents = write_csv_to_stream(
                headers=visitor.headers, data=data
            ).getvalue()
            if proxy.dry_run:
                log.info(f"DRY RUN: Would have uploaded {filename}")
                continue

            project.upload_file_contents(
                filename=filename, contents=contents, content_type="text/csv"
            )
            project_ids_list.append(project.id)
            log.info(f"Successfully uploaded {filename}")

        if project_ids_list and downstream_gears:
            JobPoll.wait_for_batched_group(
                proxy=proxy,
                project_ids_list=project_ids_list,
                downstream_gears=downstream_gears,
            )
