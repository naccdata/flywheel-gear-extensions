"""Module for processing input data file."""

import json
import logging
from abc import ABC, abstractmethod
from json.decoder import JSONDecodeError
from typing import Any, Dict, Literal, Mapping, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import (
    SubjectError,
    VisitInfo,
)
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from keys.keys import DefaultValues, FieldNames
from outputs.errors import (
    JSONLocation,
    ListErrorWriter,
    empty_field_error,
    empty_file_error,
    get_error_log_name,
    malformed_file_error,
    previous_visit_failed_error,
    system_error,
    update_error_log_and_qc_metadata,
)

from form_qc_app.definitions import DefinitionsLoader
from form_qc_app.validate import RecordValidator

log = logging.getLogger(__name__)

FailedStatus = Literal['NONE', 'SAME', 'DIFFERENT']


class FileProcessor(ABC):
    """Abstract class for processing the input file and running data quality
    checks."""

    def __init__(self, *, pk_field: str, module: str, date_field: str,
                 project: ProjectAdaptor, error_writer: ListErrorWriter,
                 gear_name: str) -> None:
        self._pk_field = pk_field
        self._module = module
        self._date_field = date_field
        self._project = project
        self._error_writer = error_writer
        self._gear_name = gear_name
        self._error_log_template = {
            "ptid": FieldNames.PTID,
            "visitdate": self._date_field
        }

    @abstractmethod
    def validate_input(
            self, *,
            input_wrapper: InputFileWrapper) -> Optional[Dict[str, Any]]:
        """Validates the input file before proceeding with data quality checks.

        Args:
            input_wrapper: Wrapper object for gear input file

        Returns:
            Dict[str, Any]: None if required info missing, else input record as dict
        """

    @abstractmethod
    def load_schema_definitions(
        self, *, rule_def_loader: DefinitionsLoader, input_data: Dict[str, Any]
    ) -> tuple[Dict[str, Mapping], Optional[Dict[str, Dict]]]:
        """Loads the rule definition JSON schemas for the respective
        module/version.

        Args:
            rule_def_loader: Helper class to load rule definitions
            input_data: Input data record

        Returns:
            rule definition schema, code mapping schema (optional)

        Raises:
            DefinitionException: if error occurred while loading schemas
        """

    @abstractmethod
    def process_input(self, *, validator: RecordValidator) -> bool:
        """Process the input file and run data quality checks.

        Args:
            validator: Helper class for validating a input record

        Returns:
           bool: True if input passed validation

        Raises:
            GearExecutionError: if errors occurred while processing the input file
        """

    def update_visit_error_log(self,
                               *,
                               input_record: Dict[str, Any],
                               qc_passed: bool,
                               reset_metadata: bool = False) -> bool:
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks
            reset_metadata: reset metadata from previous runs, set True for first gear

        Returns:
            bool: True if error log updated successfully, else False
        """
        error_log_name = get_error_log_name(
            module=self._module,
            input_data=input_record,
            naming_template=self._error_log_template)

        if not error_log_name or not update_error_log_and_qc_metadata(
                error_log_name=error_log_name,
                destination_prj=self._project,
                gear_name=self._gear_name,
                state='PASS' if qc_passed else 'FAIL',
                errors=self._error_writer.errors(),
                reset_metadata=reset_metadata):
            log.warning('Failed to update error log for record %s, %s',
                        input_record[self._pk_field],
                        input_record[self._date_field])
            return False

        return True


class JSONFileProcessor(FileProcessor):
    """Class for processing JSON input file."""

    def __init__(self, *, pk_field: str, module: str, date_field: str,
                 project: ProjectAdaptor, error_writer: ListErrorWriter,
                 gear_name: str) -> None:
        super().__init__(pk_field=pk_field,
                         module=module,
                         date_field=date_field,
                         project=project,
                         error_writer=error_writer,
                         gear_name=gear_name)

    def __has_failed_visits(self) -> FailedStatus:
        """Check whether the participant has any failed previous visits.

        Returns:
            FailedStatus: Literal['NONE', 'SAME', 'DIFFERENT']

        Raises:
            GearExecutionError: If error occurred while checking for previous visits
        """
        try:
            failed_visit = self.__subject.get_last_failed_visit(self._module)
        except SubjectError as error:
            raise GearExecutionError(error) from error

        visitdate = self.__input_record[self._date_field]

        if failed_visit:
            same_file = (failed_visit.file_id and failed_visit.file_id
                         == self.__file_id) or (failed_visit.filename
                                                == self.__filename)
            # if failed visit date is same as current visit date
            if failed_visit.visitdate == visitdate:
                # check whether it is the same file
                if same_file:
                    return 'SAME'
                else:
                    raise GearExecutionError(
                        'Two different files exists with same visit date '
                        f'{visitdate} for subject {self.__subject.label} '
                        f'module {self._module} - '
                        f'{failed_visit.filename} and {self.__filename}')

            # same file but the visit date is different from previously recorded value
            if same_file:
                log.warning(
                    'In {subject.label}/{module}, visit date updated from %s to %s',
                    failed_visit.visitdate, visitdate)
                return 'SAME'

            # has a failed previous visit
            if failed_visit.visitdate < visitdate:
                self._error_writer.write(
                    previous_visit_failed_error(failed_visit.filename))
                return 'DIFFERENT'

        return 'NONE'

    def validate_input(
            self, *,
            input_wrapper: InputFileWrapper) -> Optional[Dict[str, Any]]:
        """Validates a JSON input file for a participant visit. Check whether
        all required fields are present in the input data. Check whether
        primary key matches with the Flywheel subject label in the project.

        Args:
            input_wrapper: Wrapper object for gear input file

        Returns:
            Dict[str, Any]: None if required info missing, else input record as dict
        """
        with open(input_wrapper.filepath, mode='r',
                  encoding='utf-8') as file_obj:
            try:
                input_data = json.load(file_obj)
            except (JSONDecodeError, TypeError) as error:
                self._error_writer.write(malformed_file_error(str(error)))
                return None

        if not input_data:
            self._error_writer.write(empty_file_error())
            return None

        if not input_data.get(self._pk_field):
            self._error_writer.write(empty_field_error(self._pk_field))
            return None

        if not input_data.get(self._date_field):
            self._error_writer.write(empty_field_error(self._date_field))
            return None

        if not input_data.get(FieldNames.FORMVER):
            self._error_writer.write(empty_field_error(FieldNames.FORMVER))
            return None

        subject_lbl = input_data[self._pk_field]
        subject = self._project.find_subject(subject_lbl)
        if not subject:
            message = ('Failed to retrieve subject '
                       f'{subject_lbl} in project {self._project.label}')
            log.error(message)
            self._error_writer.write(
                system_error(message, JSONLocation(key_path=self._pk_field)))
            return None

        self.__input_record = input_data
        self.__file_id = input_wrapper.file_id
        self.__filename = input_wrapper.filename
        self.__subject = subject

        return self.__input_record

    def load_schema_definitions(
        self, *, rule_def_loader: DefinitionsLoader, input_data: Dict[str, Any]
    ) -> tuple[Dict[str, Mapping], Optional[Dict[str, Dict]]]:
        """Loads the rule definition JSON schemas for the respective
        module/version. Checks for optional form submissions and loads the
        appropriate schema.

        Args:
            rule_def_loader: Helper class to load rule definitions
            input_data: Input data record

        Returns:
            rule definition schema, code mapping schema (optional)

        Raises:
            DefinitionException: if error occurred while loading schemas
        """

        optional_forms = rule_def_loader.get_optional_forms_submission_status(
            input_data=input_data, module=self._module)

        skip_forms = []
        # Check which form is submitted for C2/C2T and skip the definition for other
        if self._module == DefaultValues.UDS_MODULE:
            c2c2t_mode = None
            try:  # noqa: SIM105
                c2c2t_mode = int(input_data.get(FieldNames.C2C2T, 2))
            except ValueError:
                pass

            skip_forms = ['c2'] if c2c2t_mode == DefaultValues.C2TMODE else [
                'c2t'
            ]

        return rule_def_loader.load_definition_schemas(
            input_data=input_data,
            module=self._module,
            optional_forms=optional_forms,
            skip_forms=skip_forms)

    def process_input(self, *, validator: RecordValidator) -> bool:
        """Process the JSON record for the participant visit.

        Args:
            validator: Helper class for validating the input record

        Returns:
            bool: True if input passed validation

        Raises:
            GearExecutionError: if errors occurred while processing the input record
        """

        valid = False

        visitdate = self.__input_record[self._date_field]

        # check whether there are any pending visits for this participant/module
        failed_visit = self.__has_failed_visits()

        # if there are no failed visits or last failed visit is the current visit
        # run error checks on visit file
        if failed_visit in ['NONE', 'SAME']:
            valid = validator.process_data_record(record=self.__input_record)
            if not valid:
                visit_info = VisitInfo(filename=self.__filename,
                                       file_id=self.__file_id,
                                       visitdate=visitdate)
                self.__subject.set_last_failed_visit(self._module, visit_info)
            # reset failed visit metadata in Flywheel
            elif failed_visit == 'SAME':
                self.__subject.reset_last_failed_visit(self._module)

        if not self.update_visit_error_log(input_record=self.__input_record,
                                           qc_passed=valid):
            raise GearExecutionError('Failed to update error log for visit '
                                     f'{self.__subject.label}, {visitdate}')

        return valid
