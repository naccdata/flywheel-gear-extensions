import logging
from abc import ABC, abstractmethod
from datetime import datetime as dt
from logging import Logger
from typing import Optional, TextIO

from dates.form_dates import DEFAULT_DATE_TIME_FORMAT

from outputs.error_models import FileError, FileErrorList
from outputs.outputs import CSVWriter

log = logging.getLogger(__name__)


class ErrorWriter(ABC):
    """Abstract class for error write."""

    def __init__(self):
        """Initializer - sets the timestamp to time of creation."""
        self.__timestamp = (dt.now()).strftime(DEFAULT_DATE_TIME_FORMAT)

    def set_timestamp(self, error: FileError) -> None:
        """Assigns the timestamp to the error."""
        error.timestamp = self.__timestamp

    @abstractmethod
    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Writes the error to the output target of implementing class."""
        pass


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
        self.__log.error(error.model_dump_json(by_alias=True, indent=4))


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

    def __init__(self, stream: TextIO, container_id: str, fw_path: str) -> None:
        self.__writer = CSVWriter(stream=stream, fieldnames=FileError.fieldnames())
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

    def __init__(
        self,
        container_id: str,
        fw_path: str,
        errors: Optional[FileErrorList] = None,
    ) -> None:
        super().__init__(container_id, fw_path)
        self.__errors = FileErrorList([]) if errors is None else errors

    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Captures error for writing to metadata.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        self.prepare_error(error, set_timestamp)
        self.__errors.append(error)

    def errors(self) -> FileErrorList:
        """Returns serialized list of accumulated file errors.

        Returns:
          List of serialized FileError objects
        """
        return self.__errors

    def clear(self):
        """Clear the errors list."""
        self.__errors.clear()

    def has_errors(self) -> bool:
        """Check whether there are errors to report.

        Returns:
          True if there are errors to report, else False
        """
        return len(self.__errors) > 0
