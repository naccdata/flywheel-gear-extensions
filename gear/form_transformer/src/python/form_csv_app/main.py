"""Defines CSV to JSON transformations."""

import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, TextIO

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    get_error_log_name,
    missing_field_error,
    partially_failed_file_error,
    unexpected_value_error,
    update_error_log_and_qc_metadata,
)
from transform.transformer import BaseRecordTransformer, TransformerFactory
from uploads.uploader import FormJSONUploader

log = logging.getLogger(__name__)


class CSVTransformVisitor(CSVVisitor):
    """Class to transform a participant visit CSV record."""

    def __init__(self,
                 *,
                 req_fields: List[str],
                 transformed_records: DefaultDict[str, Dict[str, Dict[str,
                                                                      Any]]],
                 error_writer: ListErrorWriter,
                 transformer_factory: TransformerFactory,
                 gear_name: str,
                 project: Optional[ProjectAdaptor] = None) -> None:
        self.__req_fields = req_fields
        self.__transformed = transformed_records
        self.__error_writer = error_writer
        self.__transformer_factory = transformer_factory
        self.__has_module_field = False
        self.__gear_name = gear_name
        self.__project = project
        self.__module: Optional[str] = None
        self.__transformer: Optional[BaseRecordTransformer] = None
        # TODO - change to get from template
        self.__date_field = FieldNames.DATE_COLUMN
        self.__error_log_template = {
            "ptid": FieldNames.PTID,
            "visitdate": self.__date_field
        }

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

        if not set(self.__req_fields).issubset(set(header)):
            self.__error_writer.write(
                missing_field_error(set(self.__req_fields)))
            return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Apply necessary transformations on the given data row. Assumes all
        records in the CSV file belongs to the same module.

        Args:
          row: the dictionary for a row from a CSV file
          line_num: line number in the CSV file

        Returns:
          True if the row was processed without error, False otherwise
        """

        self.__error_writer.clear()

        found_all = True
        empty_fields = set()
        for field in self.__req_fields:
            if field not in row or not row[field]:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self.__error_writer.write(empty_field_error(
                empty_fields, line_num))
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        # If module expected set module
        if self.has_module():
            self.__set_module(row)
            # All records in the CSV file must belongs to the same module.
            if not self.__check_module(row=row, line_num=line_num):
                self.__update_visit_error_log(input_record=row,
                                              qc_passed=False)
                return False

        # Set transformer for the module
        if not self.__transformer:
            self.__transformer = self.__transformer_factory.create(
                self.__module, self.__error_writer)

        transformed_row = self.__transformer.transform(row, line_num)
        if not transformed_row:
            self.__update_visit_error_log(input_record=row, qc_passed=False)
            return False

        # for the records that passed transformation, only obtain the log name
        # error metadata will be updated when the acquisition file is uploaded
        error_log_name = self.__update_visit_error_log(input_record=row,
                                                       qc_passed=True,
                                                       update=False)
        if not error_log_name:
            return False

        subject_lbl = transformed_row[FieldNames.NACCID]
        self.__transformed[subject_lbl][error_log_name] = transformed_row

        return True

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
        if not self.has_module():
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

    def __update_visit_error_log(
            self,
            *,
            input_record: Dict[str, Any],
            qc_passed: bool,
            update: Optional[bool] = True) -> Optional[str]:
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks
            update (optional): whether to update the log or return only name

        Returns:
            str (optional): error log name if update successful, else None
        """

        if not self.__project or not self.module:
            log.warning(
                'Parent project or module not specified to upload visit error log'
            )
            return None

        error_log_name = get_error_log_name(
            module=self.module,
            input_data=input_record,
            naming_template=self.__error_log_template)

        if not update or not error_log_name:
            return error_log_name

        if not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=self.__project,
                gear_name=self.__gear_name,
                state='PASS' if qc_passed else 'FAIL',
                errors=self.__error_writer.errors()):
            log.error('Failed to update error log for visit %s, %s',
                      input_record[FieldNames.PTID],
                      input_record[self.__date_field])
            return None

        return error_log_name


def notify_upload_errors():
    # TODO: send an email to nacc_dev@uw.edu
    pass


def run(*,
        input_file: TextIO,
        destination: ProjectAdaptor,
        transformer_factory: TransformerFactory,
        error_writer: ListErrorWriter,
        gear_name: str,
        downstream_gears: Optional[List[str]] = None) -> bool:
    """Reads records from the input file and transforms each into a JSON file.
    Uploads the JSON file to the respective acquisition in Flywheel.

    Args:
        input_file: the input file
        destination: Flyhweel project container
        transformer_factory: the factory for column transformers
        error_writer: the writer for error output
        gear_name: gear name
        downstream_gears: list of downstream gears

    Returns:
        bool: True if transformation/upload successful
    """

    # TODO - get the required fields from template
    req_fields_list = [
        FieldNames.NACCID, FieldNames.MODULE, FieldNames.VISITNUM,
        FieldNames.DATE_COLUMN, FieldNames.FORMVER
    ]

    transformed_records: DefaultDict[str, Dict[str,
                                               Dict[str,
                                                    Any]]] = defaultdict(dict)
    visitor = CSVTransformVisitor(req_fields=req_fields_list,
                                  transformed_records=transformed_records,
                                  error_writer=error_writer,
                                  transformer_factory=transformer_factory,
                                  gear_name=gear_name,
                                  project=destination)
    result = read_csv(input_file=input_file,
                      error_writer=error_writer,
                      visitor=visitor,
                      clear_errors=True)

    if not len(transformed_records) > 0:
        return result

    if not visitor.has_module():
        raise GearExecutionError(
            'Module information not found in the input file')

    uploader = FormJSONUploader(
        project=destination,
        module=visitor.module,  # type: ignore
        gear_name=gear_name,
        error_writer=error_writer,
        downstream_gears=downstream_gears)
    upload_status = uploader.upload(transformed_records)
    if not upload_status:
        error_writer.clear()
        error_writer.write(partially_failed_file_error())
        notify_upload_errors()

    return result and upload_status
