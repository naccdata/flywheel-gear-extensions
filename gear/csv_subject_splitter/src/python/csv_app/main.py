"""Defines CSV to JSON transformations."""

import logging
from typing import Any, Dict, List, Set, TextIO

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    empty_field_error,
    missing_field_error,
)
from uploads.provenance import FileProvenance
from uploads.uploader import JSONUploader, UploaderError

log = logging.getLogger(__name__)


class CSVSplitVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(
        self,
        *,
        provenance: FileProvenance,
        req_fields: Set[str],
        project: ProjectAdaptor,
        uploader: JSONUploader,
        error_writer: ErrorWriter,
    ) -> None:
        self.__provenance = provenance
        self.__req_fields = req_fields
        self.__project = project
        self.__uploader = uploader
        self.__error_writer = error_writer

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to process rows using the given header columns.
        If the header doesn't have required fields writes an error.

        Args:
          header: the list of header names

        Returns:
          True if the header has all required fields, False otherwise
        """

        if not self.__req_fields.issubset(set(header)):
            self.__error_writer.write(missing_field_error(self.__req_fields))
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
        empty_fields = set()
        for field in self.__req_fields:
            if field not in row or row[field] is None:
                empty_fields.add(field)

        if empty_fields:
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

        if not self.__provenance.set_provenance(file):
            log.error("Failed to set provenance on %s", file.name)
            return False

        return True


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(
    *,
    provenance: FileProvenance,
    uploader: JSONUploader,
    input_file: TextIO,
    destination: ProjectAdaptor,
    error_writer: ErrorWriter,
    preserve_case: bool,
    req_fields: Set[str],
) -> bool:
    """Reads records from the input file and creates a JSON file for each.
    Uploads the JSON file to the respective acquisition in Flywheel.

    Args:
        provenance: The FileProvenance to track source
        uploader: JSONUploader; will handle uploading each record
        input_file: the input file
        destination: Flywheel project container
        error_writer: the writer for error output
        preserve_case: Whether or not to preserve header case
        req_fields: Required fields (e.g. an error is reported if empty)
            NACCID is always required/added to this set
    Returns:
        bool: True if upload successful
    """
    req_fields.add(FieldNames.NACCID)

    result = read_csv(
        input_file=input_file,
        error_writer=error_writer,
        visitor=CSVSplitVisitor(
            provenance=provenance,
            req_fields=req_fields,
            project=destination,
            uploader=uploader,
            error_writer=error_writer,
        ),
        preserve_case=preserve_case,
    )

    return result
