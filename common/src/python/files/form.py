from abc import ABC, abstractmethod
from typing import Optional

from flywheel.models.file_entry import FileEntry


class Form(ABC):

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
        return self.__file_object.get("info").get("forms",
                                                  {}).get("json").get(key)
