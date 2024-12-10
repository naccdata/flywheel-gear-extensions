"""Defines CSV to JSON transformations."""

import logging
from typing import Any, Dict, List, Optional, TextIO

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import (
    ErrorWriter,
    empty_field_error,
    missing_field_error,
    unexpected_value_error,
)
from transform.transformer import BaseRecordTransformer, TransformerFactory

from csv_app.uploader import FormJSONUploader, JSONUploader, LabelTemplate, RecordUploader

log = logging.getLogger(__name__)


class CSVTransformVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(self, *, req_fields: List[str],
                 transformed_records: Dict[str, List[Dict[str, Any]]],
                 error_writer: ErrorWriter,
                 transformer_factory: TransformerFactory) -> None:
        self.__req_fields = req_fields
        self.__transformed = transformed_records
        self.__error_writer = error_writer
        self.__transformer_factory = transformer_factory
        self.__has_module_field = False
        self.__module: Optional[str] = None
        self.__transformer: Optional[BaseRecordTransformer] = None

    def has_module(self) -> bool:
        """Indicates whether a module field was detected in the file header.

        Returns:
          True if a module field was found in the file header. False, otherwise.
        """
        return self.__has_module_field

    @property
    def module(self) -> Optional[str]:
        """Returns the detected module for the CSV file."""
        return self.__module

    def visit_header(self, header: List[str]) -> bool:
        """Prepares the visitor to process rows using the given header columns.
        If the header doesn't have required fields writes an error.

        Args:
          header: the list of header names

        Returns:
          True if the header has all required fields, False otherwise
        """

        self.__has_module_field = FieldNames.MODULE in header

        found_all = True
        for field in self.__req_fields:
            if field not in header:
                found_all = False
                self.__error_writer.write(missing_field_error(field))

        return found_all

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Apply necessary transformations on the given data row. Assumes all
        records in the CSV file belongs to the same module.

        Args:
          row: the dictionary for a row from a CSV file
          line_num: line number in the CSV file

        Returns:
          True if the row was processed without error, False otherwise
        """

        found_all = True
        for field in self.__req_fields:
            if field not in row or not row[field]:
                found_all = False
                self.__error_writer.write(empty_field_error(field, line_num))

        if not found_all:
            return False

        # Set module
        # Assumes all records in the CSV file belongs to the same module.
        if self.__has_module_field:
            self.__set_module(row)
            if not self.__check_module(row=row, line_num=line_num):
                return False

        # Set transformer for the module
        if not self.__transformer:
            self.__transformer = self.__transformer_factory.create(
                self.__module, self.__error_writer)

        transformed_row = self.__transformer.transform(row, line_num)
        if transformed_row:
            subject_lbl = transformed_row[FieldNames.NACCID]
            visits = self.__transformed.get(subject_lbl)
            if not visits:
                visits = []
                self.__transformed[subject_lbl] = visits
            visits.append(transformed_row)

        return bool(transformed_row)

    def __get_module(self, row: Dict[str, Any]) -> Optional[str]:
        """Returns the module from the row.

        Args:
          row: the input row
        Returns:
          the module in uppercase if one exists in row. None, otherwise.
        """
        module = row.get(FieldNames.MODULE)
        return module.upper() if module else None

    def __set_module(self, row: Dict[str, Any]) -> None:
        """Sets the module for the visitor from the row.

        If the row has no module field, sets to None.

        Args:
          row: the input row
        """
        if not self.__module:
            self.__module = self.__get_module(row)

    def __check_module(self, row: Dict[str, Any], line_num: int) -> bool:
        """Checks the module in the row matches the module in this visitor.

        If the file has no module field, returns True.

        Args:
          row: the input row
          line_num: the line number of row
        Returns:
          True if module matches, or no module expected. False, otherwise.
        """
        if not self.__has_module_field:
            return True

        row_module = self.__get_module(row)
        if self.__module == row_module:
            return True

        self.__error_writer.write(
            unexpected_value_error(
                field=FieldNames.MODULE,
                value=row_module,  # type: ignore
                expected=self.__module,  # type: ignore
                line=line_num))
        return False


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(*, input_file: TextIO, destination: ProjectAdaptor,
        transformer_factory: TransformerFactory,
        template_map: Dict[str,
                           LabelTemplate], error_writer: ErrorWriter) -> bool:
    """Reads records from the input file and transforms each into a JSON file.
    Uploads the JSON file to the respective aquisition in Flywheel.

    Args:
        input_file: the input file
        proxy: Flywheel proxy object
        project: Flyhweel project container
        admin_project: Flywheel admin_project container
        error_writer: the writer for error output
    Returns:
        bool: True if transformation/upload successful
    """

    transformed_records: Dict[str, List[Dict[str, Any]]] = {}
    visitor = CSVTransformVisitor(req_fields=[FieldNames.NACCID],
                                  transformed_records=transformed_records,
                                  error_writer=error_writer,
                                  transformer_factory=transformer_factory)
    result = read_csv(input_file=input_file,
                      error_writer=error_writer,
                      visitor=visitor)

    if not len(transformed_records) > 0:
        return result

    if visitor.has_module():
        uploader: RecordUploader = FormJSONUploader(project=destination,
                                    module=visitor.module)  # type: ignore
    else:
        uploader = JSONUploader(project=destination, template_map=template_map)
    upload_status = uploader.upload(transformed_records)
    if not upload_status:
        notify_upload_errors()

    return result and upload_status
