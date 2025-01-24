"""Error reporting module."""

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from keys.keys import FieldNames, RuleLabels
from outputs.errors import (
    CSVLocation,
    FileError,
    JSONLocation,
    ListErrorWriter,
    system_error,
)
from pydantic import BaseModel, ValidationError
from redcap.redcap_connection import REDCapConnectionError, REDCapReportConnection
from redcap.redcap_project import REDCapProject

log = logging.getLogger(__name__)

COMPOSITE_RULES = [RuleLabels.COMPAT, RuleLabels.TEMPORAL, RuleLabels.GDS]


class ErrorDescription(BaseModel):
    """Represents an error description object for a NACC QC check."""
    error_code: str
    error_type: str
    var_name: str
    form_name: str
    check_type: str
    short_desc: str
    full_desc: str

    @classmethod
    def create(cls, entry: Dict[str, str]) -> 'ErrorDescription':
        """Creates ErrorDescription object from a dictionary input.

        Args:
          entry: the dictionary with error info

        Returns:
          The ErrorDescription object
        """
        entry = {k: v.lower() for k, v in entry.items()}
        return ErrorDescription.model_validate(entry)


class ErrorStore(ABC):
    """Base class to retrieve NACC QC checks information from a database."""

    # List of error cheks by error code
    __errors_list: ClassVar[Dict[str, ErrorDescription]] = {}

    def __init__(self, preload: bool = False) -> None:
        """

        Args:
            preload (optional): If True, load QC check info at initialization.
                                Defaults to False.
        """
        self.__preload = preload
        if preload:
            self.load_error_checks()

    @property
    def errors_list(self) -> Dict[str, ErrorDescription]:
        """Returns errors_list."""
        return self.__errors_list

    @abstractmethod
    def load_error_checks(self):
        """This method loads the QC checks info from the database."""

    @abstractmethod
    def query_error_database(
            self, error_codes: List[str]) -> Dict[str, ErrorDescription]:
        """Query the error checks database for the given error codes.

        Args:
            error_codes: NACC QC check codes

        Returns:
            Dict[str, ErrorDescription]: Error info dictionary by error code
        """

        return {}

    def get_qc_check_info(
            self, error_codes: List[str]) -> Dict[str, ErrorDescription]:
        """Retrieve QC check information by error code.

        Args:
            error_codes: NACC QC check codes

        Returns:
            Dict[str, ErrorDescription]: Error info for the given error codes
        """

        qc_checks_list: Dict[str, ErrorDescription] = {}
        if self.__preload:
            for error_code in error_codes:
                if error_code in self.errors_list:
                    qc_checks_list[error_code] = self.errors_list[error_code]
        else:
            qc_checks_list = self.query_error_database(error_codes)

        return qc_checks_list


class REDCapErrorStore(ErrorStore):
    """Class to retrieve QC checks information from a REDCap project."""

    def __init__(self,
                 *,
                 redcap_con: Optional[REDCapReportConnection] = None,
                 preload: bool = False) -> None:
        self.__redcap_con = redcap_con
        super().__init__(preload)

    def load_error_checks(self):
        """This method loads the QC checks info from REDCap report."""

        if not self.__redcap_con:
            log.error('REDCap connection not set')
            return

        try:
            records_list = self.__redcap_con.get_report_records()
        except REDCapConnectionError as error:
            log.error(error.message)
            return

        for record in records_list:
            try:
                error_desc = ErrorDescription.create(record)
                self.errors_list[record['error_code']] = error_desc
            except ValidationError as error:
                log.warning("Failed to create error description from %s: %s",
                            record, error)

    def query_error_database(self, error_codes) -> Dict[str, ErrorDescription]:
        """Query the error checks database for the given error codes.

        Args:
            error_codes: NACC QC check codes

        Returns:
            Dict[str, ErrorDescription]: Error info dictionary by error code
        """

        qc_checks_list: Dict[str, ErrorDescription] = {}
        record_ids = []
        for error_code in error_codes:
            if error_code in self.errors_list:
                qc_checks_list[error_code] = self.errors_list[error_code]
            else:
                record_ids.append(error_code)

        # retrieve the error codes not found in the cache from the database
        if record_ids and self.__redcap_con:
            fields = list(ErrorDescription.__annotations__.keys())
            try:
                redcap_prj = REDCapProject.create(self.__redcap_con)
                records_list = redcap_prj.export_records(record_ids=record_ids,
                                                         fields=fields)
                for record in records_list:
                    error_code = record['error_code']  # type: ignore
                    try:
                        error_desc = ErrorDescription.create(
                            record)  # type: ignore
                        qc_checks_list[error_code] = error_desc
                        self.errors_list[error_code] = error_desc
                    except ValidationError as error:
                        log.warning(
                            "Failed to create error description from %s: %s",
                            record, error)
            except REDCapConnectionError as error:
                log.error('%s for %s', error.message, record_ids)

        return qc_checks_list


def replace_nullable_with_required(rule: str, code_schema: Dict[str,
                                                                Dict]) -> bool:
    """If code mapping not found in the schema for nullable rule, use the same
    code as required rule if it is defined in the schema.

    Args:
        rule: rule name
        code_schema: schema mapping validation rule -> NACC code

    Returns:
        bool: True if a match found, else False
    """
    if rule == RuleLabels.NULLABLE and RuleLabels.REQUIRED in code_schema:
        code_schema[rule] = code_schema[RuleLabels.REQUIRED]
        return True

    return False


def is_composite_rule(rule: str) -> bool:
    """Check whether the given rule is a composite rule that consists of
    multiple conditions.

    Args:
        rule: rule name

    Returns:
        bool: True if rule is in composite rules list
    """
    if rule in COMPOSITE_RULES:
        return True

    return False


class ErrorComposer():
    """This class composes the error metadata required for the error report.

    If error code mapping is available, NACC QC check information will
    be pulled from a database and included in the error metadata.
    Otherwise, error metadata composed using error info generated by
    nacc-form-validator library. https://github.com/naccdata/nacc-form-
    validator
    """

    def __init__(
        self,
        *,
        input_data: Dict[str, str],
        error_store: ErrorStore,
        dict_errors: Dict[str, List[str]],
        error_messages: Dict[int, str],
        error_writer: ListErrorWriter,
    ) -> None:
        """Initialize the ErrorComposer.

        Args:
            input_data: input data record that raised the error
            error_store: datastore to retrieve error check details
            dict_errors: list of error messages by variable
            error_messages: list of error messages by validator error codes
            error_writer: the error output writer
        """

        self.__input_data = input_data
        self.__error_store = error_store
        self.__dict_errors = dict_errors
        self.__error_messages = error_messages
        self.__error_writer = error_writer

    def get_qc_check_info(
            self, error_codes: List[str]) -> Dict[str, ErrorDescription]:
        """Retrieve QC check information for the given error codes from DB.

        Args:
            error_codes: NACC QC check codes

        Returns:
            Dict[str, ErrorDescription]: error descriptions by error code
            (returns empty dictionary if there's an issue with DB connection)
        """

        return self.__error_store.get_qc_check_info(error_codes)

    def __get_qc_error_object(self,
                              *,
                              error_type: str,
                              error_code: str,
                              error_msg: str,
                              value: str,
                              field: str,
                              line_number: Optional[int] = None) -> FileError:
        """Creates a QCError object from the given input.

        Args:
            error_type: error type - Error or Alert
            error_code: error code
            error_msg: error message
            value: current value of the variable in input data
            field: variable name
            line_number (optional):line # in CSV file if record is from CSV

        Returns:
            FileError object
        """

        return FileError(
            error_type=error_type,  # type: ignore
            error_code=error_code,
            location=CSVLocation(line=line_number, column_name=field)
            if line_number else JSONLocation(key_path=field),
            value=value,
            message=error_msg,
            ptid=str(self.__input_data[FieldNames.PTID])
            if FieldNames.PTID in self.__input_data else None,
            visitnum=str(self.__input_data[FieldNames.VISITNUM])
            if FieldNames.VISITNUM in self.__input_data else None)

    def __write_qc_error_no_code(self,
                                 *,
                                 error_obj: Any,
                                 field: str,
                                 line_number: Optional[int] = None):
        """Write QC error metadata when NACC QC check info not available.

        Args:
            error_obj: cerberus.errors.ValidationError object
            field: variable name
            line_number (optional): line # in CSV file if record is from CSV
        """
        error_msg = self.__error_messages[error_obj.code].format(
            *error_obj.info,
            constraint=error_obj.constraint,
            field=field,
            value=error_obj.value)

        qc_error = self.__get_qc_error_object(error_type='error',
                                              error_code='qc-error',
                                              error_msg=error_msg,
                                              value=str(error_obj.value),
                                              field=field,
                                              line_number=line_number)
        self.__error_writer.write(qc_error)

    def __write_qc_error(self,
                         *,
                         error_desc: ErrorDescription,
                         value: str,
                         line_number: Optional[int] = None,
                         other_codes: Optional[str] = None):
        """Write QC error metadata when NACC QC check info available.

        Args:
            error_desc: QC check information for the error
            value: variable value
            line_number (optional): line # in CSV file if record is from CSV
            other_codes (optional): any related error codes if available
        """

        error_codes = error_desc.error_code
        if other_codes:
            error_codes += ',' + other_codes
        qc_error = self.__get_qc_error_object(error_type=error_desc.error_type,
                                              error_code=error_codes,
                                              error_msg=error_desc.full_desc,
                                              value=value,
                                              field=error_desc.var_name,
                                              line_number=line_number)
        self.__error_writer.write(qc_error)

    def __fill_error_metadata_with_qc_check_info(
            self,
            *,
            error_codes: List[str],
            error_info_map: Dict[str, Dict],
            line_number: Optional[int] = None):
        """Pull NACC QC check info from the errors database and write detailed
        error metadata.

        Args:
            error_codes: NACC QC check codes
            error_info_map: dict mapping NACC code to validator error object
            line_number (optional): line # in CSV file if record is from CSV
        """

        qc_check_info = self.get_qc_check_info(error_codes)
        for error_code in error_info_map:
            error_obj = error_info_map[error_code]['error']
            field = error_info_map[error_code]['field']
            other_codes = error_info_map[error_code]['other']
            if error_code in qc_check_info:
                error_desc = qc_check_info[error_code]
                self.__write_qc_error(error_desc=error_desc,
                                      value=str(error_obj.value),
                                      line_number=line_number,
                                      other_codes=other_codes)
            else:
                log.warning('NACC QC check code %s not found in the errors DB',
                            error_code)
                self.__write_qc_error_no_code(error_obj=error_obj,
                                              field=field,
                                              line_number=line_number)

    def _map_error_with_qc_check_code(self,
                                      *,
                                      field: str,
                                      code_schema: Dict,
                                      validator_errors: List[Any],
                                      err_info_map: Dict[str, Dict],
                                      nacc_error_codes: List[str],
                                      line_number: Optional[int] = None):
        """Map validator generated errors with NACC QC check code using the
        code map schema.

        Args:
            field: variable name
            code_schema: schema describing validation rule->NACC code mapping
            validator_errors: List of cerberus.errors.ValidationError objects
            err_info_map: Dict to store NACC code->error object mapping
            nacc_error_codes: List to store NACC codes found during validation
            line_number (optional): line # in CSV file if record is from CSV
        """

        for error in validator_errors:
            # Skip if this error is a sub-error generated by a nested rule
            # Ex. anyof, allof, etc., it will be handled at top level key
            if error.rule != error.schema_path[1]:
                continue

            if (error.rule not in code_schema
                    and not replace_nullable_with_required(
                        error.rule, code_schema)):
                log.warning(
                    'NACC error code not found '
                    'for variable %s rule %s - %s', field, error.rule,
                    error.schema_path)
                self.__write_qc_error_no_code(error_obj=error,
                                              field=field,
                                              line_number=line_number)
                continue

            if is_composite_rule(error.rule):
                checks = code_schema[error.rule]
                rule_index = error.info[0]
                for check in checks:
                    code_index = check[RuleLabels.INDEX]
                    if rule_index == code_index and check[RuleLabels.CODE]:
                        first_code, other_codes = self._split_nacc_error_codes(
                            check[RuleLabels.CODE])
                        nacc_error_codes.append(first_code)
                        err_info_map[first_code] = {
                            'error': error,
                            'field': field,
                            'other': other_codes
                        }
            elif code_schema[error.rule][RuleLabels.CODE]:
                first_code, other_codes = self._split_nacc_error_codes(
                    code_schema[error.rule][RuleLabels.CODE])
                nacc_error_codes.append(first_code)
                err_info_map[first_code] = {
                    'error': error,
                    'field': field,
                    'other': other_codes
                }

    # pylint: disable=(no-self-use)
    def _split_nacc_error_codes(self, codes: str) -> Tuple[str, Optional[str]]:
        """Splits the NACC error codes list.

        Args:
            codes: comma separated list of NACC error codes

        Returns:
            Tuple[str, Optional[str]]: first code, rest of the codes
        """
        codes_list = codes.split(",", 1)
        other = codes_list[1] if len(codes_list) > 1 else None

        return codes_list[0], other

    def compose_system_errors_metadata(self,
                                       line_number: Optional[int] = None):
        """Compose error metadata for system errors.

        Args:
            line_number (optional): line # in CSV file if record is from CSV
        """

        log.error('System error(s) occurred during validation, '
                  'please fix the issues below and retry '
                  'or contact the system administrator.')
        log.error(self.__dict_errors)
        for field, err_list in self.__dict_errors.items():
            for error_msg in err_list:
                self.__error_writer.write(
                    system_error(
                        error_msg,
                        CSVLocation(line=line_number, column_name=field)
                        if line_number else JSONLocation(key_path=field)))

    def compose_minimal_error_metadata(self,
                                       line_number: Optional[int] = None):
        """Compose error metadata when error code info not available, error
        message will display the library generated error string.

        Args:
            line_number (optional): line # in CSV file if record is from CSV
        """

        for field, err_list in self.__dict_errors.items():
            value = ''
            if field in self.__input_data:
                value = self.__input_data[field]
            for error_msg in err_list:
                qc_error = self.__get_qc_error_object(error_type='error',
                                                      error_code='qc-error',
                                                      error_msg=error_msg,
                                                      value=value,
                                                      field=field,
                                                      line_number=line_number)
                self.__error_writer.write(qc_error)

    # pylint: disable=(too-many-locals, too-many-branches)
    def compose_detailed_error_metadata(self,
                                        *,
                                        error_tree: Dict[str, Any],
                                        err_code_map: Dict[str, Dict],
                                        line_number: Optional[int] = None):
        """Compose detailed error metadata using the error code map to retrieve
        information from the NACC QC checks database.

        Args:
            error_tree: dict like object with detailed error information
            err_code_map: schema to map NACC error codes with validator errors
            line_number (optional): line # in CSV file if record is from CSV

        Notes:
            check https://docs.python-cerberus.org/errors.html for info on
            how to use the error_tree object
        """

        err_info_map: Dict[str, Dict] = {}
        nacc_error_codes: List[str] = []
        for field in self.__dict_errors:
            value = ''
            if field in self.__input_data:
                value = str(self.__input_data[field])

            if field not in err_code_map or field not in error_tree:
                err_list = self.__dict_errors[field]
                for error_msg in err_list:
                    qc_error = self.__get_qc_error_object(
                        error_type='error',
                        error_code='unknown-field',
                        error_msg=error_msg,
                        value=value,
                        field=field,
                        line_number=line_number)
                    self.__error_writer.write(qc_error)
                continue

            code_schema = err_code_map[field]
            validator_errors = error_tree[field].errors
            self._map_error_with_qc_check_code(
                field=field,
                code_schema=code_schema,
                validator_errors=validator_errors,
                err_info_map=err_info_map,
                nacc_error_codes=nacc_error_codes,
                line_number=line_number)

        self.__fill_error_metadata_with_qc_check_info(
            error_codes=nacc_error_codes,
            error_info_map=err_info_map,
            line_number=line_number)
