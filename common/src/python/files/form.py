"""Defines base class for forms."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from flywheel.models.file_entry import FileEntry


class Form(ABC):
    """Base class for forms."""

    def __init__(self, file_object: FileEntry) -> None:
        self.__file_object = file_object

    def get_file_id(self) -> str:
        """Returns the file ID for the form file."""
        return self.__file_object.id

    def get_variable(self, key: str) -> Optional[Any]:
        """Get the data value for the specified key from the form data file.

        Args:
            key (str): attribute key

        Returns:
            attribute value
        """
        return self.__file_object.get("info", {}).get("forms",
                                                      {}).get("json").get(key)

    def get_info(self) -> Dict[str, Any]:
        """Returns the info object for the file of this form."""
        return self.__file_object.info

    def update_info(self, values: Dict[str, Any]) -> None:
        """Updates the custom info for the file of this form.

        Args:
          values: the dictionary to update with
        """
        self.__file_object.update_info(values)

    @abstractmethod
    def get_form_date(self) -> Optional[datetime]:
        """Gets the date of the session of form.

        Returns:
          the date of session
        """
        return None

    def is_form(self,
                name: Optional[str] = None,
                version: Optional[str] = None) -> bool:
        """Checks if the file object is a form. Also, checks module name and
        version if provided.

        Note: tests the info of the file.

        Args:
          name: the module name (optional)
          version: the version (optional)
        Returns:
          True if the file is a form, and matches name and version if given.
          False otherwise.
        """
        if not self.__file_object.get("info").get("forms"):
            return False

        if not name:
            return True

        module = self.get_variable('module')
        assert module, "assume module is set"
        if name.lower() != module.lower():
            return False

        if not version:
            return True

        form_version = self.get_variable('formver')
        assert form_version, "assume formver is set"
        return version.lower() != str(form_version).lower()
