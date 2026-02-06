"""Module for processing CSV files."""

# Assumes all the records in the CSV file belongs to same module/version/packet
# Note: Optional forms check is not implemented for CSV files
# Currently only enrollment module is submitted as a CSV file,
# and does not require optional forms check.
# Need to change the way we load rule definitions if we
# have to support optional forms check for CSV inputs.

import logging
import os
from csv import DictReader
from io import StringIO
from typing import Any, Dict, List, Mapping, Optional

from configs.ingest_configs import FormProjectConfigs
from datastore.forms_store import FormsStore
from flywheel import FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from inputs.csv_reader import CSVVisitor, read_csv
from keys.keys import DefaultValues
from nacc_common.error_models import VisitKeys
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    empty_field_error,
    missing_field_error,
    unknown_field_error,
)
from outputs.outputs import CSVWriter
from preprocess.preprocessor import FormPreprocessor, PreprocessingContext

from form_qc_app.definitions import DefinitionsLoader
from form_qc_app.processor import FileProcessor
from form_qc_app.validate import RecordValidator

log = logging.getLogger(__name__)


class EnrollmentFormVisitor(CSVVisitor):
    """Class to validate form data uploaded as a CSV file.

    Requires the input CSV has primary-key column and module column.
    """

    def __init__(
        self,
        required_fields: set[str],
        date_field: str,
        error_writer: ListErrorWriter,
        processor: "CSVFileProcessor",
        validator: Optional[RecordValidator] = None,
        output_stream: Optional[StringIO] = None,
    ) -> None:
        """

        Args:
            required_fields: list of required field
            date_field: date field for enrollment form
            error_writer: error metadata writer
            processor: file processor
            validator (optional): helper for validating input records
            output_stream (optional): output stream
        """
        self.__required_fields = required_fields
        self.__date_field = date_field
        self.__error_writer = error_writer
        self.__processor = processor
        self.__validator = validator
        self.__output_stream = output_stream
        self.__output_writer: Optional[CSVWriter] = None
        self.__header: Optional[List[str]] = None
        self.__valid_rows = 0

    def __get_output_writer(self) -> CSVWriter:
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        output stream is provided at initialization and header has been
        set.
        """

        if not self.__output_writer:
            assert self.__output_stream, "Output stream must be provided"
            assert self.__header, "CSV header must be set before adding any data rows"
            self.__output_writer = CSVWriter(
                stream=self.__output_stream, fieldnames=self.__header
            )

        return self.__output_writer

    def visit_header(self, header: List[str]) -> bool:
        """Validates the header fields in file. If the header doesn't have
        required fields writes an error. Also, if validation schema provided,
        rejects the file if there are any unknown fields in the header.

        Args:
          header: the list of header names

        Returns:
          True if required fields found in the header, False otherwise
        """

        if not self.__required_fields.issubset(set(header)):
            self.__error_writer.write(missing_field_error(self.__required_fields))
            return False

        if self.__validator:
            unknown_fields = set(header).difference(
                set(self.__validator.get_validation_schema().keys())
            )

            if unknown_fields:
                self.__error_writer.write(unknown_field_error(unknown_fields))
                return False

        self.__header = header

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Validates a row from the CSV file.

        If the row doesn't have required fields writes an error.

        Args:
          row: the dictionary from the CSV row (DictReader)
          line_num: the line number of the row

        Returns:
          True if required fields occur in the row, False otherwise
        """

        # processing a new row, clear previous errors if any
        self.__error_writer.clear()

        found_all = True
        empty_fields = set()
        for field in self.__required_fields:
            if row.get(field) is None:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self.__error_writer.write(
                empty_field_error(
                    field=empty_fields,
                    line=line_num,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )
            if self.__validator:
                self.__processor.update_visit_error_log(
                    input_record=row, qc_passed=False, reset_qc_metadata="ALL"
                )
            return False

        valid = True
        if self.__validator:
            valid = self.__validator.process_data_record(
                record=row, line_number=line_num
            )
            self.__processor.update_visit_error_log(
                input_record=row, qc_passed=valid, reset_qc_metadata="ALL"
            )

        if valid and self.__output_stream:
            writer = self.__get_output_writer()
            writer.write(row)
            self.__valid_rows += 1

        return valid

    def get_valid_record_count(self) -> int:
        """Returns the number of rows that passed validation."""
        return self.__valid_rows


class CSVFileProcessor(FileProcessor):
    """Class for processing CSV input file.

    Assumes the entire CSV file is for same module/version. (used for
    enrollment form processing).
    """

    def __init__(
        self,
        *,
        pk_field: str,
        module: str,
        date_field: str,
        project: ProjectAdaptor,
        error_writer: ListErrorWriter,
        form_configs: FormProjectConfigs,
        gear_name: str,
    ) -> None:
        super().__init__(
            pk_field=pk_field,
            module=module,
            date_field=date_field,
            project=project,
            error_writer=error_writer,
            form_configs=form_configs,
            gear_name=gear_name,
        )
        self.__input: Optional[InputFileWrapper] = None

    def validate_input(
        self, *, input_wrapper: InputFileWrapper
    ) -> Optional[Dict[str, Any]]:
        """Validates a CSV input file. Check whether all required fields are
        present in the header and the first data row.

        Args:
            input_wrapper: Wrapper object for gear input file

        Returns:
            Dict[str, Any]: None if required info missing, else first row as dict
        """

        if not self._module_configs:
            raise GearExecutionError(
                f"Failed to find the configurations for module {self._module}"
            )

        self.__input = input_wrapper
        with open(input_wrapper.filepath, mode="r", encoding="utf-8-sig") as file_obj:
            # Validate header and first row of the CSV file
            result = read_csv(
                input_file=file_obj,
                error_writer=self._error_writer,
                visitor=EnrollmentFormVisitor(
                    required_fields=set(self._req_fields),
                    date_field=self._date_field,
                    error_writer=self._error_writer,
                    processor=self,
                ),
                limit=1,
            )

            if not result:
                return None

            file_obj.seek(0)
            reader = DictReader(file_obj)
            first_row = next(reader)

            preprocessor = FormPreprocessor(
                form_configs=self._form_configs,
                forms_store=FormsStore(
                    ingest_project=self._project, legacy_project=None
                ),
                module=self._module,
                module_configs=self._module_configs,
                error_writer=self._error_writer,
            )

            pp_context = PreprocessingContext(input_record=first_row, line_num=1)

            if not preprocessor.is_accepted_version(pp_context=pp_context):
                return None

            return first_row

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
        return rule_def_loader.load_definition_schemas(
            input_data=input_data, module=self._module
        )

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
            raise GearExecutionError("Missing input file")

        out_stream = StringIO()
        enrl_visitor = EnrollmentFormVisitor(
            required_fields=set(self._req_fields),
            date_field=self._date_field,
            error_writer=self._error_writer,
            processor=self,
            validator=validator,
            output_stream=out_stream,
        )

        with open(self.__input.filepath, mode="r", encoding="utf-8-sig") as csv_file:
            success = read_csv(
                input_file=csv_file,
                error_writer=self._error_writer,
                visitor=enrl_visitor,
                clear_errors=True,
            )

            # If only subset of records passed validation,
            # write those to a separate output file and upload to Flywheel project
            if not success and enrl_visitor.get_valid_record_count() > 0:
                (basename, extension) = os.path.splitext(self.__input.filename)
                out_filename = f"{basename}_{DefaultValues.PROV_SUFFIX}{extension}"
                file_spec = FileSpec(
                    name=out_filename,
                    contents=out_stream.getvalue(),
                    content_type="text/csv",
                )

                try:
                    self._project.upload_file(file_spec)
                    log.info(
                        "Uploaded file %s to project %s/%s",
                        out_filename,
                        self._project.group,
                        self._project.label,
                    )
                except ApiException as error:
                    raise GearExecutionError(
                        f"Failed to upload file {out_filename} to "
                        f"{self._project.group}/{self._project.label}: {error}"
                    ) from error

            return success
