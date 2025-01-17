"""Utilities for writing errors to a error log."""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime as dt
from logging import Handler, Logger
from typing import Any, Dict, List, Literal, Optional, TextIO

from dates.form_dates import DEFAULT_DATE_FORMAT, convert_date
from flywheel.file_spec import FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import FieldNames, SysErrorCodes
from pydantic import BaseModel, ConfigDict, Field

from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)

preprocess_errors = {
    SysErrorCodes.ADCID_MISMATCH:
    "ADCID must match the ADCID of the center uploading the data",
    SysErrorCodes.IVP_EXISTS:
    "Only one Initial Visit Packet is allowed per participant",
    SysErrorCodes.DIFF_VISITDATE:
    "Two packets cannot have the same visit number (VISITNUM) " +
    "if they are from different dates (VISITDATE)",
    SysErrorCodes.DIFF_VISITNUM:
    "Two packets cannot have the same visit date(VISITDATE) " +
    "if they are from different visit numbers (VISITNUM)",
    SysErrorCodes.LOWER_FVP_VISITNUM:
    "Visit number (VISITNUM) for Follow-Up Visit Packets must be " +
    "greater than Visit number (VISITNUM) for Initial Visit Packet",
    SysErrorCodes.LOWER_I4_VISITNUM:
    "Visit number (VISITNUM) for UDSv4 Initial Visit Packet (PACKET=I4) " +
    "must be greater than Visit number (VISITNUM) for of the last UDSv3 Visit Packet",
    SysErrorCodes.LOWER_FVP_VISITDATE:
    "Follow-Up Packet visit date (VISITDATE) cannot be equal to " +
    "or from a date before the Initial Visit Packet",
    SysErrorCodes.LOWER_I4_VISITDATE:
    "To submit an Initial UDSv4 Visit Packet (PACKET=I4), participant must have "
    +
    "an existing UDSv3 Visit with visit date (VISITDATE) before the Initial I4 Packet",
    SysErrorCodes.INVALID_MODULE:
    "Provided MODULE is not in the list of currently accepted modules",
    SysErrorCodes.INVALID_PACKET:
    "Provided PACKET code is not in the list of accepted packets for this module",
    SysErrorCodes.MISSING_IVP:
    "Follow-Up visit cannot be submitted without an existing Initial Visit Packet",
    SysErrorCodes.MULTIPLE_IVP:
    "More than one IVP packet found for the participant/module",
    SysErrorCodes.INVALID_VERSION:
    "Provided FORMVER is not in the list of " +
    "accepted versions for this module"
}


class CSVLocation(BaseModel):
    """Represents location of an error in a CSV file."""
    model_config = ConfigDict(populate_by_name=True)

    line: int
    column_name: str


class JSONLocation(BaseModel):
    """Represents the location of an error in a JSON file."""
    model_config = ConfigDict(populate_by_name=True)

    key_path: str


class FileError(BaseModel):
    """Represents an error that might be found in file during a step in a
    pipeline."""
    model_config = ConfigDict(populate_by_name=True)

    timestamp: Optional[str] = None
    error_type: Literal['alert', 'error',
                        'warning'] = Field(serialization_alias='type')
    error_code: str = Field(serialization_alias='code')
    location: Optional[CSVLocation | JSONLocation] = None
    container_id: Optional[str] = None
    flywheel_path: Optional[str] = None
    value: Optional[str] = None
    expected: Optional[str] = None
    message: str
    ptid: Optional[str] = None
    visitnum: Optional[str] = None

    @classmethod
    def fieldnames(cls) -> List[str]:
        """Gathers the serialized field names for the class."""
        result = []
        for fieldname, field_info in cls.model_fields.items():
            if field_info.serialization_alias:
                result.append(field_info.serialization_alias)
            else:
                result.append(fieldname)
        return result


def identifier_error(line: int,
                     value: str,
                     field: str = 'ptid',
                     message: Optional[str] = None) -> FileError:
    """Creates a FileError for an unrecognized PTID error in a CSV file.

    Tags the error type as 'error:identifier'

    Args:
      line: the line where error occurred
      value: the value of the PTID
    Returns:
      a FileError object initialized for an identifier error
    """
    error_message = message if message else 'Unrecognized participant ID'
    return FileError(error_type='error',
                     error_code='identifier-error',
                     location=CSVLocation(line=line, column_name=field),
                     value=value,
                     message=error_message)


def empty_file_error() -> FileError:
    """Creates a FileError for an empty input file."""
    return FileError(error_type='error',
                     error_code='empty-file',
                     message='Empty input file')


def missing_header_error() -> FileError:
    """Creates a FileError for a missing header."""
    return FileError(error_type='error',
                     error_code='missing-header',
                     message='No file header found')


def invalid_header_error(message: Optional[str] = None) -> FileError:
    """Creates a FileError for an invalid header."""
    message = message if message else "Invalid header"
    return FileError(error_type='error',
                     error_code='invalid-header',
                     message=message)


def missing_field_error(field: str | set[str]) -> FileError:
    """Creates a FileError for missing field(s) in header."""
    return FileError(
        error_type='error',
        error_code='missing-field',
        message=f'Missing one or more required field(s) {field} in the header')


def empty_field_error(field: str | set[str],
                      line: Optional[int] = None,
                      message: Optional[str] = None) -> FileError:
    """Creates a FileError for empty field(s)."""
    error_message = message if message else f'Required field(s) {field} cannot be blank'

    return FileError(error_type='error',
                     error_code='empty-field',
                     location=CSVLocation(line=line, column_name=str(field))
                     if line else JSONLocation(key_path=str(field)),
                     message=error_message)


def malformed_file_error(error: str) -> FileError:
    """Creates a FileError for a malformed input file."""
    return FileError(error_type='error',
                     error_code='malformed-file',
                     message=f'Malformed input file: {error}')


def unexpected_value_error(field: str,
                           value: str,
                           expected: str,
                           line: int,
                           message: Optional[str] = None) -> FileError:
    """Creates a FileError for an unexpected value.

    Args:
      field: the field name
      value: the unexpected value
      expected: the expected value
      line: the line number
      message: the error message
    Returns:
      the constructed FileError
    """
    error_message = message if message else (
        f'Expected {expected} for field {field}')
    return FileError(error_type='error',
                     error_code='unexpected-value',
                     value=value,
                     expected=expected,
                     location=CSVLocation(line=line, column_name=field),
                     message=error_message)


def unknown_field_error(field: str | set[str]) -> FileError:
    """Creates a FileError for unknown field(s) in file header."""
    return FileError(error_type='error',
                     error_code='unknown-field',
                     message=f'Unknown field(s) {field} in header')


def system_error(
        message: str,
        error_location: Optional[CSVLocation | JSONLocation] = None,
        error_type: Literal['alert', 'error',
                            'warning'] = 'error') -> FileError:
    """Creates a FileError object for a system error.

    Args:
      message: error message
      error_location (optional): CSV or JSON file location related to the error
      error_type: error type, defaults to "error"
    Returns:
      a FileError object initialized for system error
    """
    return FileError(error_type=error_type,
                     error_code='system-error',
                     location=error_location,
                     message=message)


def previous_visit_failed_error(prev_visit: str) -> FileError:
    """Creates a FileError when participant has failed previous visits."""
    return FileError(error_type='error',
                     error_code='failed-previous-visit',
                     message=(f'Visit file {prev_visit} has to be approved '
                              'before evaluating any subsequent visits'))


def preprocessing_error(field: str,
                        value: str,
                        line: int,
                        error_code: Optional[str] = None,
                        message: Optional[str] = None,
                        ptid: Optional[str] = None,
                        visitnum: Optional[str] = None) -> FileError:
    """Creates a FileError for pre-processing error.

    Args:
      field: the field name
      value: the unexpected value
      line: the line number
      error_code (optional): pre-processing error code
      message (optional): the error message
      ptid (optional): PTID if known
      visitnum (optional): visitnum if known

    Returns:
      the constructed FileError
    """

    error_message = message if message else (
        f'Pre-processing error for field {field} value {value}')

    if error_code:
        error_message = preprocess_errors.get(error_code, error_message)

    return FileError(
        error_type='error',
        error_code=error_code if error_code else 'preprocess-error',
        value=value,
        location=CSVLocation(line=line, column_name=field),
        message=error_message,
        ptid=ptid,
        visitnum=visitnum)


def partially_failed_file_error() -> FileError:
    """Creates a FileError when input file is not fully approved."""
    return FileError(
        error_type='error',
        error_code='partially-failed',
        message=('Some records in this file did not pass validation, '
                 'check the respective record level qc status'))


def existing_participant_error(field: str,
                               value: str,
                               line: int,
                               message: Optional[str] = None) -> FileError:
    """Creates a FileError for unexpected existing participant."""
    error_message = message if message else ('Participant exists for PTID '
                                             f'{value}')
    return FileError(error_type='error',
                     error_code='participant-exists',
                     location=CSVLocation(column_name=field, line=line),
                     message=error_message)


class ErrorWriter(ABC):
    """Abstract class for error write."""

    def __init__(self):
        """Initializer - sets the timestamp to time of creation."""
        self.__timestamp = (dt.now()).strftime('%Y-%m-%d %H:%M:%S')

    def set_timestamp(self, error: FileError) -> None:
        """Assigns the timestamp to the error."""
        error.timestamp = self.__timestamp

    @abstractmethod
    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Writes the error to the output target of implementing class."""
        pass


# pylint: disable=(too-few-public-methods)
class LogErrorWriter(ErrorWriter):
    """Writes errors to logger."""

    def __init__(self, log: Logger) -> None:
        self.__log = log
        super().__init__()

    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Writes the error to the logger.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        if set_timestamp:
            self.set_timestamp(error)
        self.__log.error(json.dumps(error.model_dump(by_alias=True), indent=4))


class UserErrorWriter(ErrorWriter):
    """Abstract class for a user error writer."""

    def __init__(self, container_id: str, fw_path: str) -> None:
        self.__container_id = container_id
        self.__flywheel_path = fw_path
        super().__init__()

    def set_container(self, error: FileError) -> None:
        """Assigns the container ID and Flywheel path for the error."""
        error.container_id = self.__container_id
        error.flywheel_path = self.__flywheel_path

    def prepare_error(self, error, set_timestamp: bool = True) -> None:
        """Prepare the error by adding container and timestamp information.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        self.set_container(error)
        if set_timestamp:
            self.set_timestamp(error)


class StreamErrorWriter(UserErrorWriter):
    """Writes FileErrors to a stream as CSV."""

    def __init__(self, stream: TextIO, container_id: str,
                 fw_path: str) -> None:
        self.__writer = CSVWriter(stream=stream,
                                  fieldnames=FileError.fieldnames())
        super().__init__(container_id, fw_path)

    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Writes the error to the output stream with flywheel hierarchy
        information filled in for the reference file.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        self.prepare_error(error, set_timestamp)
        self.__writer.write(error.model_dump(by_alias=True))


class ListErrorWriter(UserErrorWriter):
    """Collects FileErrors to file metadata."""

    def __init__(self, container_id: str, fw_path: str) -> None:
        super().__init__(container_id, fw_path)
        self.__errors: List[Dict[str, Any]] = []

    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Captures error for writing to metadata.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        self.prepare_error(error, set_timestamp)
        self.__errors.append(error.model_dump(by_alias=True))

    def errors(self) -> List[Dict[str, Any]]:
        """Returns serialized list of accumulated file errors.

        Returns:
          List of serialized FileError objects
        """
        return self.__errors

    def clear(self):
        """Clear the errors list."""
        self.__errors.clear()


class ListHandler(Handler):
    """Defines a handler to keep track of logged info."""

    def __init__(self):
        super().__init__()
        self.__logs = []

    def emit(self, record):
        self.__logs.append(json.loads(record.msg))

    def get_logs(self):
        return self.__logs


def update_error_log_and_qc_metadata(*,
                                     error_log_name: str,
                                     destination_prj: ProjectAdaptor,
                                     gear_name: str,
                                     state: str,
                                     errors: List[Dict[str, Any]],
                                     reset_metadata: bool = False) -> bool:
    """Update project level error log file and store error metadata in
    file.info.qc.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_name: gear that generated errors
        state: gear execution status [PASS|FAIL|NA]
        errors: list of error objects, expected to be JSON dicts
        reset_metadata: reset metadata from previous runs, set to True for first gear

    Returns:
        bool: True if metadata update is successful, else False
    """

    info: Dict[str, Any] = {"qc": {}}
    contents = ''

    current_log = destination_prj.get_file(error_log_name)
    # append to existing error details if any
    if current_log:
        current_log = current_log.reload()
        if current_log.info and 'qc' in current_log.info and not reset_metadata:
            info = current_log.info
        contents = (current_log.read()).decode('utf-8')  # type: ignore

    timestamp = (dt.now()).strftime('%Y-%m-%d %H:%M:%S')
    contents += f'{timestamp} QC Status: {gear_name.upper()} - {state.upper()}\n'
    for error in errors:
        contents += json.dumps(error) + '\n'

    error_file_spec = FileSpec(name=error_log_name,
                               contents=contents,
                               content_type='text',
                               size=len(contents))
    try:
        destination_prj.upload_file(error_file_spec)
        destination_prj.reload()
        new_file = destination_prj.get_file(error_log_name)
    except ApiException as error:
        log.error(f'Failed to upload file {error_log_name} to '
                  f'{destination_prj.group}/{destination_prj.label}: {error}')
        return False

    info["qc"][gear_name] = {
        "validation": {
            "state": state.upper(),
            "data": errors
        }
    }
    try:
        new_file.update_info(info)
    except ApiException as error:
        log.error('Error in setting QC metadata in file %s - %s',
                  error_log_name, error)
        return False

    return True


def get_error_log_name(
        *,
        module: str,
        input_data: Dict[str, Any],
        naming_template: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Derive error log name based on visit data.

    Args:
        module: module label
        input_data: input visit record
        naming_template (optional): error log naming template for module

    Returns:
        str (optional): error log name or None
    """

    if not naming_template:
        naming_template = {
            "ptid": FieldNames.PTID,
            "visitdate": FieldNames.DATE_COLUMN
        }

    ptid = input_data.get(naming_template.get('ptid', FieldNames.PTID))
    visitdate = input_data.get(
        naming_template.get('visitdate', FieldNames.DATE_COLUMN))

    if not ptid or not visitdate:
        return None

    normalized_date = convert_date(date_string=visitdate,
                                   date_format=DEFAULT_DATE_FORMAT)
    if not normalized_date:
        return None

    return f'{ptid}_{normalized_date}_{module.lower()}_qc-status.log'
