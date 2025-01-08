"""Module for processing CSV files."""

# Assumes all the records in the CSV file belongs to same module/version/packet
# Note: Optional forms check is not implemented for CSV files
# Currently only enrollment module is submitted as a CSV file,
# and does not require optional forms check.
# Need to change the way we load rule definitions if we
# have to support optional forms check for CSV inputs.

from csv import DictReader
from typing import Any, Dict, List, Mapping, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import FieldNames
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    missing_field_error,
    unknown_field_error,
)

from form_qc_app.definitions import DefinitionsLoader
from form_qc_app.processor import FileProcessor
from form_qc_app.validate import RecordValidator


class EnrollmentFormVisitor(CSVVisitor):
    """Class to validate form data uploaded as a CSV file.

    Requires the input CSV has primary-key column and module column.
    """

    def __init__(self,
                 required_fields: set[str],
                 error_writer: ListErrorWriter,
                 processor: 'CSVFileProcessor',
                 validator: Optional[RecordValidator] = None) -> None:
        """
        Args:
          required_fields: list of required fields
          error_writer: the error output writer
        """
        self.__required_fields = required_fields
        self.__error_writer = error_writer
        self.__processor = processor
        self.__validator = validator

    def visit_header(self, header: List[str]) -> bool:
        """Validates the header fields in file. If the header doesn't have
        primary key field, date field, or formver, writes an error. Also, if
        validation schema provided, rejects the file if there are any unknown
        fields in the header.

        Args:
          header: the list of header names

        Returns:
          True if required fields found in the header, False otherwise
        """

        if not self.__required_fields.issubset(set(header)):
            self.__error_writer.write(
                missing_field_error(self.__required_fields))
            return False

        if self.__validator:
            unknown_fields = set(header).difference(
                set(self.__validator.get_validation_schema().keys()))

            if unknown_fields:
                self.__error_writer.write(unknown_field_error(unknown_fields))
                return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Validates a row from the CSV file.

        If the row doesn't have `<primary key>`, formver writes an error.

        Args:
          row: the dictionary from the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if required fields occur in the row, False otherwise
        """

        self.__error_writer.clear()

        found_all = True
        empty_fields = set()
        for field in self.__required_fields:
            if field not in row or not row[field]:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self.__error_writer.write(empty_field_error(
                empty_fields, line_num))
            self.__processor.update_visit_error_log(input_record=row,
                                                    qc_passed=False)
            return False

        if self.__validator:
            valid = self.__validator.process_data_record(record=row,
                                                         line_number=line_num)

            if not valid:
                self.__processor.update_visit_error_log(input_record=row,
                                                        qc_passed=valid,
                                                        reset_metadata=True)

            return valid

        return True


class CSVFileProcessor(FileProcessor):
    """Class for processing CSV input file.

    Assumes the entire CSV file is for same module/version. (used for
    enrollment form processing).
    """

    def __init__(self, *, pk_field: str, module: str, date_field: str,
                 project: ProjectAdaptor, error_writer: ListErrorWriter,
                 gear_name: str) -> None:
        super().__init__(pk_field=pk_field,
                         module=module,
                         date_field=date_field,
                         project=project,
                         error_writer=error_writer,
                         gear_name=gear_name)
        self.__required_fields = {pk_field, date_field, FieldNames.FORMVER}
        self.__input: Optional[InputFileWrapper] = None

    def validate_input(
            self, *,
            input_wrapper: InputFileWrapper) -> Optional[Dict[str, Any]]:
        """Validates a CSV input file. Check whether all required fields are
        present in the header and the first data row.

        Args:
            input_wrapper: Wrapper object for gear input file

        Returns:
            Dict[str, Any]: None if required info missing, else first row as dict
        """

        self.__input = input_wrapper
        with open(input_wrapper.filepath, mode='r',
                  encoding='utf-8') as file_obj:
            # Validate header and first row of the CSV file
            result = read_csv(input_file=file_obj,
                              error_writer=self._error_writer,
                              visitor=EnrollmentFormVisitor(
                                  required_fields=self.__required_fields,
                                  error_writer=self._error_writer,
                                  processor=self),
                              limit=1)

            if not result:
                return None

            file_obj.seek(0)
            reader = DictReader(file_obj)
            return next(reader)

    def load_schema_definitions(
        self, rule_def_loader: DefinitionsLoader, input_data: Dict[str, Any]
    ) -> tuple[Dict[str, Mapping], Optional[Dict[str, Dict]]]:
        """Loads the rule definition JSON schemas for the respective
        module/version. Assumes the entire CSV file is for same module/version.

        Args:
            rule_def_loader: Helper class to load rule definitions
            input_data: Input data record

        Returns:
            rule definition schema, code mapping schema (optional)

        Raises:
            DefinitionException: if error occurred while loading schemas
        """
        return rule_def_loader.load_definition_schemas(input_data=input_data,
                                                       module=self._module)

    def process_input(self, *, validator: RecordValidator) -> bool:
        """Reads the CSV file and apply NACC data quality checks to each
        record.

        Args:
            validator: Helper class for validating a input record

        Returns:
            bool: True if input passed validation

        Raises:
            GearExecutionError: if errors occurred while processing the input file
        """

        if not self.__input:
            raise GearExecutionError('Missing input file')

        enrl_visitor = EnrollmentFormVisitor(
            required_fields=self.__required_fields,
            error_writer=self._error_writer,
            processor=self,
            validator=validator)

        with open(self.__input.filepath, mode='r',
                  encoding='utf-8') as csv_file:
            success = read_csv(input_file=csv_file,
                               error_writer=self._error_writer,
                               visitor=enrl_visitor,
                               clear_errors=True)

            return success
