"""Utilities for writing errors to a CSV error file."""
from abc import ABC, abstractmethod
from datetime import datetime as dt
from typing import Any, Dict, List, Literal, Optional, TextIO

from pydantic import BaseModel, ConfigDict, Field

from outputs.outputs import CSVWriter


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

    error_type: Literal['alert', 'error'] = Field(serialization_alias='type')
    error_code: str = Field(serialization_alias='code')
    location: Optional[CSVLocation | JSONLocation] = None
    container_id: Optional[str] = None
    flywheel_path: Optional[str] = None
    value: Optional[str] = None
    expected: Optional[str] = None
    message: str
    timestamp: Optional[str] = None
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
                     error_code='identifier',
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


def missing_field_error(field: str) -> FileError:
    """Creates a FileError for a missing field in header."""
    return FileError(error_type='error',
                     error_code='missing-field',
                     message=f'Missing field "{field}" in the header')


def empty_field_error(field: str,
                      line: Optional[int] = None,
                      message: Optional[str] = None) -> FileError:
    """Creates a FileError for an empty field."""
    error_message = message if message else f'Field {field} is required'
    return FileError(error_type='error',
                     error_code='empty-field',
                     location=CSVLocation(line=line, column_name=field)
                     if line else JSONLocation(key_path=field),
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


def unknown_field_error(field: str) -> FileError:
    """Creates a FileError for an unknown field in file header."""
    return FileError(error_type='error',
                     error_code='unknown-field',
                     message=f'Unknown field {field} in header')


def system_error(
    message: str,
    error_location: Optional[CSVLocation | JSONLocation] = None,
) -> FileError:
    """Creates a FileError object for a system error.

    Args:
      message: error message
      error_location [Optional]: CSV or JSON file location related to the error
    Returns:
      a FileError object initialized for system error
    """
    return FileError(error_type='error',
                     error_code='system-error',
                     location=error_location,
                     message=message)


def previous_visit_failed_error(prev_visit: str) -> FileError:
    """Creates a FileError when participant has failed previous visits."""
    return FileError(error_type='error',
                     error_code='failed-previous-visit',
                     message=(f'Visit file {prev_visit} has to be approved '
                              'before evaluating any subsequent visits'))


class ErrorWriter(ABC):
    """Abstract base class for error writer."""

    def __init__(self, container_id: str, fw_path: str) -> None:
        self.__container_id = container_id
        self.__flyweel_path = fw_path
        self.__timestamp = (dt.now()).strftime('%Y-%m-%d %H:%M:%S')

    @abstractmethod
    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Writes the error to the output target of implementing class."""

    def set_container(self, error: FileError) -> None:
        """Assigns the container ID and Flywheel path for the error."""
        error.container_id = self.__container_id
        error.flywheel_path = self.__flyweel_path

    def set_timestamp(self, error: FileError) -> None:
        """Assigns the timestamp the error."""
        error.timestamp = self.__timestamp


# pylint: disable=(too-few-public-methods)
class StreamErrorWriter(ErrorWriter):
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
        self.set_container(error)
        if set_timestamp:
            self.set_timestamp(error)
        self.__writer.write(error.model_dump(by_alias=True))


class ListErrorWriter(ErrorWriter):
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
        self.set_container(error)
        if set_timestamp:
            self.set_timestamp(error)
        self.__errors.append(error.model_dump(by_alias=True))

    def errors(self) -> List[Dict[str, Any]]:
        """Returns serialized list of accumulated file errors.

        Returns:
          List of serialized FileError objects
        """
        return self.__errors
