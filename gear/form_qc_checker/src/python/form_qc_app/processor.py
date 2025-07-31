"""Module for processing input data file."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Literal, Mapping, Optional

from configs.ingest_configs import ErrorLogTemplate, FormProjectConfigs
from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import (
    SubjectAdaptor,
    SubjectError,
    VisitInfo,
)
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from keys.keys import DefaultValues, FieldNames, MetadataKeys
from outputs.error_logger import (
    MetadataCleanupFlag,
    get_error_log_name,
    update_error_log_and_qc_metadata,
)
from outputs.error_models import JSONLocation
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    empty_field_error,
    empty_file_error,
    malformed_file_error,
    previous_visit_failed_error,
    system_error,
)

from form_qc_app.definitions import DefinitionsLoader
from form_qc_app.validate import RecordValidator

log = logging.getLogger(__name__)

FailedStatus = Literal["NONE", "SAME", "DIFFERENT"]


class FileProcessor(ABC):
    """Abstract class for processing the input file and running data quality
    checks."""

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
        self._pk_field = pk_field
        self._module = module
        self._date_field = date_field
        self._project = project
        self._error_writer = error_writer
        self._form_configs = form_configs
        self._gear_name = gear_name
        self._module_configs = self._form_configs.module_configs.get(self._module)
        self._req_fields = self._set_required_fields()
        self._errorlog_template = self._set_error_log_template()

    @abstractmethod
    def validate_input(
        self, *, input_wrapper: InputFileWrapper
    ) -> Optional[Dict[str, Any]]:
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

    def _set_required_fields(self) -> List[str]:
        """Retrieve list of required field names form module ingest configs.

        Returns:
            List[str]: list of required field names for the module
        """
        req_fields = (
            self._module_configs.required_fields
            if self._module_configs and self._module_configs.required_fields
            else []
        )
        if self._pk_field not in req_fields:
            req_fields.append(self._pk_field)
        if self._date_field not in req_fields:
            req_fields.append(self._date_field)
        if FieldNames.FORMVER not in req_fields:
            req_fields.append(FieldNames.FORMVER)

        return req_fields

    def _set_error_log_template(self) -> ErrorLogTemplate:
        """Get the error log naming template from module configs.

        Returns:
            ErrorLogTemplate: error log template for the module
        """
        if self._module_configs and self._module_configs.errorlog_template:
            return self._module_configs.errorlog_template

        return ErrorLogTemplate(id_field=FieldNames.PTID, date_field=self._date_field)

    def update_visit_error_log(
        self,
        *,
        input_record: Dict[str, Any],
        qc_passed: bool,
        reset_qc_metadata: MetadataCleanupFlag = "NA",
    ) -> bool:
        """Update error log file for the visit and store error metadata in
        file.info.qc.

        Args:
            input_record: input visit record
            qc_passed: whether the visit passed QC checks
            reset_qc_metadata: flag to reset metadata from previous runs:
                            ALL - reset all, for the first gear in submission pipeline.
                            GEAR - reset only current gear metadata from previous runs.
                            NA - do not reset (Default)

        Returns:
            bool: True if error log updated successfully, else False
        """

        error_log_name = get_error_log_name(
            module=self._module,
            input_data=input_record,
            errorlog_template=self._errorlog_template,
        )

        if not error_log_name or not update_error_log_and_qc_metadata(
            error_log_name=error_log_name,
            destination_prj=self._project,
            gear_name=self._gear_name,
            state="PASS" if qc_passed else "FAIL",
            errors=self._error_writer.errors(),
            reset_qc_metadata=reset_qc_metadata,
        ):
            log.warning(
                "Failed to update error log for record %s, %s",
                input_record[self._pk_field],
                input_record[self._date_field],
            )
            return False

        return True


class JSONFileProcessor(FileProcessor):
    """Class for processing JSON input file."""

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
        supplement_data: Optional[Dict[str, Any]] = None,
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
        self.__subject: SubjectAdaptor
        self.__file_entry: FileEntry
        self.__supplement_data = supplement_data

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
            same_file = (
                failed_visit.file_id
                and failed_visit.file_id == self.__file_entry.file_id
            ) or (failed_visit.filename == self.__file_entry.name)
            # if failed visit date is same as current visit date
            if failed_visit.visitdate == visitdate:
                # check whether it is the same file
                if same_file:
                    return "SAME"
                else:
                    raise GearExecutionError(
                        "Two different files exists with same visit date "
                        f"{visitdate} for subject {self.__subject.label} "
                        f"module {self._module} - "
                        f"{failed_visit.filename} and {self.__file_entry.name}"
                    )

            # same file but the visit date is different from previously recorded value
            if same_file:
                log.warning(
                    "In {subject.label}/{module}, visit date updated from %s to %s",
                    failed_visit.visitdate,
                    visitdate,
                )
                return "SAME"

            # has a failed previous visit
            if failed_visit.visitdate < visitdate:
                self._error_writer.write(
                    previous_visit_failed_error(failed_visit.filename)
                )
                return "DIFFERENT"

        return "NONE"

    def __update_validated_timestamp(self) -> None:
        """Set/update the validation timestamp in file.info."""
        timestamp = (datetime.now(timezone.utc)).strftime(DEFAULT_DATE_TIME_FORMAT)
        self.__file_entry = self.__file_entry.reload()
        self.__file_entry.update_info({MetadataKeys.VALIDATED_TIMESTAMP: timestamp})

    def validate_input(
        self, *, input_wrapper: InputFileWrapper
    ) -> Optional[Dict[str, Any]]:
        """Validates a JSON input file for a participant visit. Check whether
        all required fields are present in the input data. Check whether
        primary key matches with the Flywheel subject label in the project.

        Args:
            input_wrapper: Wrapper object for gear input file
            form_configs: Form ingest configurations

        Returns:
            Dict[str, Any]: None if required info missing, else input record as dict
        """
        with open(input_wrapper.filepath, mode="r", encoding="utf-8-sig") as file_obj:
            try:
                input_data = json.load(file_obj)
            except (JSONDecodeError, TypeError) as error:
                self._error_writer.write(malformed_file_error(str(error)))
                return None

        if not input_data:
            self._error_writer.write(empty_file_error())
            return None

        found_all = True
        empty_fields = set()
        for field in self._req_fields:
            if input_data.get(field) is None:
                empty_fields.add(field)
                found_all = False

        if not found_all:
            self._error_writer.write(empty_field_error(empty_fields))
            return None

        subject_lbl = input_data[self._pk_field]
        subject = self._project.find_subject(subject_lbl)
        if not subject:
            message = (
                "Failed to retrieve subject "
                f"{subject_lbl} in project {self._project.label}"
            )
            log.error(message)
            self._error_writer.write(
                system_error(message, JSONLocation(key_path=self._pk_field))
            )
            return None

        self.__input_record = input_data
        self.__file_entry = self._project.proxy.get_file(input_wrapper.file_id)
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
            input_data=input_data, module=self._module
        )

        skip_forms = []
        # Check which form is submitted for C2/C2T and skip the definition for other
        if self._module == DefaultValues.UDS_MODULE:
            c2c2t_mode = None
            try:  # noqa: SIM105
                c2c2t_mode = int(input_data.get(FieldNames.C2C2T, 2))
            except ValueError:
                pass

            skip_forms = ["c2"] if c2c2t_mode == DefaultValues.C2TMODE else ["c2t"]

        return rule_def_loader.load_definition_schemas(
            input_data=input_data,
            module=self._module,
            optional_forms=optional_forms,
            skip_forms=skip_forms,
            supplement_data=self.__supplement_data,
        )

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
        if failed_visit in ["NONE", "SAME"]:
            # merge supplement input if provided,
            # any duplicate fields should be replaced by current input
            valid = validator.process_data_record(
                record=(self.__supplement_data | self.__input_record)
                if self.__supplement_data
                else self.__input_record
            )
            if not valid:
                visit_info = VisitInfo(
                    filename=self.__file_entry.name,
                    file_id=self.__file_entry.file_id,
                    visitdate=visitdate,
                )
                self.__subject.set_last_failed_visit(self._module, visit_info)
            # reset failed visit metadata in Flywheel
            elif failed_visit == "SAME":
                self.__subject.reset_last_failed_visit(self._module)

            # update last validated timestamp in file.info metadata
            self.__update_validated_timestamp()

        if not self.update_visit_error_log(
            input_record=self.__input_record, qc_passed=valid, reset_qc_metadata="GEAR"
        ):
            raise GearExecutionError(
                "Failed to update error log for visit "
                f"{self.__subject.label}, {visitdate}"
            )

        return valid
