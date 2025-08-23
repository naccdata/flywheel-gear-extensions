"""Defines CSV to JSON transformations."""

import logging
from typing import Any, Dict, List

from configs.ingest_configs import UploadTemplateInfo
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_adaptor.hierarchy_creator import HierarchyCreationClient
from gear_execution.gear_execution import InputFileWrapper
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    empty_field_error,
    missing_field_error,
)
from uploads.acquisition import set_file_source
from uploads.uploader import JSONUploader, UploaderError

log = logging.getLogger(__name__)


class CSVSplitVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(
        self,
        *,
        req_fields: List[str],
        project: ProjectAdaptor,
        uploader: JSONUploader,
        error_writer: ErrorWriter,
        source_file: str,
    ) -> None:
        self.__req_fields = req_fields
        self.__project = project
        self.__uploader = uploader
        self.__error_writer = error_writer
        self.__source_file = source_file

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to process rows using the given header columns.
        If the header doesn't have required fields writes an error.

        Args:
          header: the list of header names

        Returns:
          True if the header has all required fields, False otherwise
        """

        if not set(self.__req_fields).issubset(set(header)):
            self.__error_writer.write(missing_field_error(set(self.__req_fields)))
            return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Assigns the row data to the subject by NACCID.

        Args:
          row: the dictionary for a row from a CSV file
          line_num: line number in the CSV file

        Returns:
          True if the row was processed without error, False otherwise
        """

        found_all = True
        empty_fields = set()
        for field in self.__req_fields:
            if field not in row or not row[field]:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self.__error_writer.write(empty_field_error(empty_fields, line_num))
            return False

        file = None
        try:
            file = self.__uploader.upload_record(
                subject_label=row[FieldNames.NACCID], record=row
            )
        except UploaderError as error:
            log.error("Error (line: %s): %s", line_num, str(error))
            # TODO: save error details for notification email
            return False

        if file is None:
            log.error("Failed to upload record for line %s", line_num)
            return False

        if not set_file_source(file, self.__source_file):
            log.error("Failed to set source_file on %s", file.name)
            return False

        return True


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(
    *,
    proxy: FlywheelProxy,
    hierarchy_client: HierarchyCreationClient,
    file_input: InputFileWrapper,
    destination: ProjectAdaptor,
    template_map: UploadTemplateInfo,
    error_writer: ErrorWriter,
    preserve_case: bool,
) -> bool:
    """Reads records from the input file and creates a JSON file for each.
    Uploads the JSON file to the respective acquisition in Flywheel.

    Args:
        file_input: the input file
        destination: Flywheel project container
        template_map: string templates for FW hierarchy labels
        error_writer: the writer for error output
        preserve_case: Whether or not to preserve header case
    Returns:
        bool: True if upload successful
    """
    with open(file_input.filepath, mode="r", encoding="utf-8-sig") as input_file:
        result = read_csv(
            input_file=input_file,
            error_writer=error_writer,
            visitor=CSVSplitVisitor(
                req_fields=[FieldNames.NACCID],
                project=destination,
                uploader=JSONUploader(
                    proxy=proxy,
                    hierarchy_client=hierarchy_client,
                    project=destination,
                    template_map=template_map,
                    environment={"filename": file_input.basename},
                ),
                error_writer=error_writer,
                source_file=file_input.filename,
            ),
            preserve_case=preserve_case,
        )

        return result
