"""Defines CSV to JSON transformations."""

import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, TextIO

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import (
    ErrorWriter,
    empty_field_error,
    missing_field_error,
)
from uploads.uploader import JSONUploader, UploadTemplateInfo

log = logging.getLogger(__name__)


class CSVSplitVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(self, *, req_fields: List[str],
                 records: DefaultDict[str, List[Dict[str, Any]]],
                 error_writer: ErrorWriter) -> None:
        self.__req_fields = req_fields
        self.__records = records
        self.__error_writer = error_writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to process rows using the given header columns.
        If the header doesn't have required fields writes an error.

        Args:
          header: the list of header names

        Returns:
          True if the header has all required fields, False otherwise
        """

        if not set(self.__req_fields).issubset(set(header)):
            self.__error_writer.write(
                missing_field_error(set(self.__req_fields)))
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
            self.__error_writer.write(empty_field_error(
                empty_fields, line_num))
            return False

        subject_lbl = row[FieldNames.NACCID]
        self.__records[subject_lbl].append(row)

        return True


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(*, input_file: TextIO, destination: ProjectAdaptor,
        environment: Dict[str, Any], template_map: UploadTemplateInfo,
        error_writer: ErrorWriter) -> bool:
    """Reads records from the input file and creates a JSON file for each.
    Uploads the JSON file to the respective aquisition in Flywheel.

    Args:
        input_file: the input file
        destination: Flywheel project container
        environment: dictionary of variables describing environment for labels
        template_map: string templates for FW hierarchy labels
        error_writer: the writer for error output
    Returns:
        bool: True if upload successful
    """

    subject_record_map: DefaultDict[str, List[Dict[str,
                                                   Any]]] = defaultdict(list)
    visitor = CSVSplitVisitor(req_fields=[FieldNames.NACCID],
                              records=subject_record_map,
                              error_writer=error_writer)
    result = read_csv(input_file=input_file,
                      error_writer=error_writer,
                      visitor=visitor)

    if not len(subject_record_map) > 0:
        return result

    uploader = JSONUploader(project=destination,
                            template_map=template_map,
                            environment=environment)
    upload_status = uploader.upload(subject_record_map)
    if not upload_status:
        notify_upload_errors()

    return result and upload_status
