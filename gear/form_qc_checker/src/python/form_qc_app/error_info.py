"""Error reporting module."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from form_qc_app.parser import Keys
from outputs.errors import JSONLocation, ListErrorWriter, QCError, system_error
from pydantic import BaseModel, ValidationError
from redcap.redcap_connection import (REDCapConnectionError,
                                      REDCapReportConnection)

log = logging.getLogger(__name__)


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
    __errors_list: Dict[str, ErrorDescription] = {}

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
    def query_error_database(self, error_codes) -> Dict[str, ErrorDescription]:
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
                log.error("Error creating error description from %s: %s",
                          record, error)

    def query_error_database(self, error_codes) -> Dict[str, ErrorDescription]:
        """Query the error checks database for the given error codes.

        Args:
            error_codes: NACC QC check codes

        Returns:
            Dict[str, ErrorDescription]: Error info dictionary by error code
        """

        qc_checks_list: Dict[str, ErrorDescription] = {}
        if self.__redcap_con:
            fields = list(ErrorDescription.__annotations__.keys())
            try:
                records_list = self.__redcap_con.export_records(
                    record_ids=error_codes, fields=fields)
                for record in records_list:
                    try:
                        error_desc = ErrorDescription.create(
                            record)  # type: ignore
                        qc_checks_list[
                            record['error_code']] = error_desc  # type: ignore
                    except ValidationError as error:
                        log.error(
                            "Error creating error description from %s: %s",
                            record, error)
            except REDCapConnectionError as error:
                log.error('%s for %s', error.message, error_codes)

        return qc_checks_list


class ErrorComposer():
    """This class composes the error metadata required for the error report."""

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

    def __get_qc_error_object(self, *, error_type: str, error_code: str,
                              error_msg: str, value: str,
                              field: str) -> QCError:
        """Creates a QCError object from the given input."""

        return QCError(
            error_type=error_type,  # type: ignore
            error_code=error_code,
            error_location=JSONLocation(key_path=field),
            value=value,
            message=error_msg,
            ptid=self.__input_data[Keys.PTID]
            if Keys.PTID in self.__input_data else None,
            visitnum=self.__input_data[Keys.VISITNUM]
            if Keys.VISITNUM in self.__input_data else None)

    def __write_qc_error_no_code(self, *, error_obj: Any, field: str):
        """Write QC error metadata when NACC QC check info not available.

        Args:
            error_obj: cerberus.errors.ValidationError object
            field: variable name
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
                                              field=field)
        self.__error_writer.write(qc_error)

    def __write_qc_error(self, error_desc: ErrorDescription, value: str):
        """Write QC error metadata when NACC QC check info available.

        Args:
            error_desc: QC check information for the error
            value: variable value
        """

        qc_error = self.__get_qc_error_object(error_type=error_desc.error_type,
                                              error_code=error_desc.error_code,
                                              error_msg=error_desc.full_desc,
                                              value=value,
                                              field=error_desc.var_name)
        self.__error_writer.write(qc_error)

    def __map_error_with_qc_check(self, *, error_codes: List[str],
                                  error_info_map: Dict[str, Dict]):
        """Map NACC QC check info with errors generated by the validator.

        Args:
            error_codes: NACC QC check codes
            error_info_map: dict mapping NACC code to validator error object
        """

        qc_check_info = self.get_qc_check_info(error_codes)
        for error_code in error_info_map:
            error_obj = error_info_map[error_code]['error']
            field = error_info_map[error_code]['field']
            if error_code in qc_check_info:
                error_desc = qc_check_info[error_code]
                self.__write_qc_error(error_desc, str(error_obj.value))
            else:
                log.warning('NACC QC check code %s not found in the errors DB',
                            error_code)
                self.__write_qc_error_no_code(error_obj=error_obj, field=field)

    def compose_system_errors_metadata(self):
        """Compose error metadata for system errors."""

        log.error('System error(s) occurred during validation, '
                  'please fix the issues below and retry '
                  'or contact the system administrator.')
        log.error(self.__dict_errors)
        for field, err_list in self.__dict_errors:
            for error_msg in err_list:
                self.__error_writer.write(
                    system_error(error_msg, JSONLocation(key_path=field)))

    def compose_minimal_error_metadata(self):
        """Compose error metadata when error code info not available, error
        message will display the library generated error string."""

        for field, err_list in self.__dict_errors:
            value = ''
            if field in self.__input_data:
                value = self.__input_data[field]
            for error_msg in err_list:
                qc_error = self.__get_qc_error_object(error_type='error',
                                                      error_code='qc-error',
                                                      error_msg=error_msg,
                                                      value=value,
                                                      field=field)
                self.__error_writer.write(qc_error)

    # pylint: disable=(too-many-locals, too-many-branches)
    def compose_detailed_error_metadata(self, *, error_tree: Dict[str, Any],
                                        err_code_map: Dict[str, Dict]):
        """Compose detailed error metadata using the error code map to retrieve
        information from the NACC QC checks database.

        Args:
            error_tree: dict like object with detailed error information
            err_code_map: schema to map NACC error codes with validator errors

        Notes:
            check https://docs.python-cerberus.org/errors.html for info on
            how to use the error_tree object
        """

        err_info_map = {}
        nacc_error_codes = []
        for field in self.__dict_errors:
            value = ''
            if field in self.__input_data:
                value = str(self.__input_data[field])

            if field not in err_code_map or field not in error_tree:
                log.warning('Error code info not found for variable %s', field)
                err_list = self.__dict_errors[field]
                for error_msg in err_list:
                    qc_error = self.__get_qc_error_object(
                        error_type='error',
                        error_code='qc-error',
                        error_msg=error_msg,
                        value=value,
                        field=field)
                    self.__error_writer.write(qc_error)
                continue

            code_shema = err_code_map[field]
            valdator_errors = error_tree[field].errors
            for error in valdator_errors:
                # Skip if this error is a sub-error generated by a nested rule
                # Ex. anyof, allof, etc., it will be handled at top level key
                if error.rule != error.schema_path[1]:
                    continue

                if error.rule not in code_shema:
                    if error.rule == Keys.NULLABLE and Keys.REQUIRED in code_shema:
                        code_shema[error.rule] = code_shema[Keys.REQUIRED]
                    else:
                        log.warning(
                            'NACC error code not found '
                            'for variable %s rule %s - %s', field, error.rule,
                            error.schema_path)
                        self.__write_qc_error_no_code(error_obj=error,
                                                      field=field)
                        continue

                if error.rule in (Keys.COMPAT, Keys.TEMPORAL):
                    checks = code_shema[error.rule]
                    rule_index = error.info[0]
                    for check in checks:
                        nacc_code = check[Keys.CODE]
                        code_index = check[Keys.INDEX]
                        if rule_index == code_index:
                            nacc_error_codes.append(nacc_code)
                            err_info_map[nacc_code] = {
                                'error': error,
                                'field': field
                            }
                else:
                    nacc_code = code_shema[error.rule][Keys.CODE]
                    nacc_error_codes.append(nacc_code)
                    err_info_map[nacc_code] = {'error': error, 'field': field}

        self.__map_error_with_qc_check(error_codes=nacc_error_codes,
                                       error_info_map=err_info_map)
