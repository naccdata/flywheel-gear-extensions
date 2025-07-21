"""Defines base class for forms."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from flywheel.models.file_entry import FileEntry


class Form(ABC):
    """Base class for forms."""

    @abstractmethod
    def __init__(self, file_object: FileEntry) -> None:
        self.__file_object = file_object

    def get_metadata(self, key: str) -> Optional[str]:
        """Get the data value for the specified key from the form data file.

        Args:
            key (str): attribute key

        Returns:
            str: attribute value
        """
        return self.__file_object.get("info").get("forms", {}).get("json").get(key)

    @abstractmethod
    def get_session_date(self) -> Optional[datetime]:
        """Gets the date of the session of form.

        Returns:
          the date of session
        """
        return None
