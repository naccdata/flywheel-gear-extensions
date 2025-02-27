"""Defines model/util classes specifically used for importing error checks into
REDCap."""
from typing import List, Optional

from pydantic import BaseModel


class ErrorCheckKey(BaseModel):
    """Pydantic model for the error check key.

    Expects to be of the form:
        CSV / MODULE / FORM_VER / PACKET /
            form_<FORM_NAME>_<PACKET>_error_checks_<type>.csv

    except for ENROLL, which is of the form:
        CSV / ENROLL / FORM_VER / naccid-enrollment-
            form_error_checks_<type>.csv
    """

    full_path: str
    csv: str
    module: str
    form_ver: str
    filename: str
    form_name: str
    packet: Optional[str] = None

    @staticmethod
    def create_from_key(key: str):
        """Create ErrorCheckKey from key.

        Args:
            key: The S3 key
        Returns:
            instantiated ErrorCheckKey
        """
        key_parts = key.split('/')

        if key_parts[0] != 'CSV':
            raise ValueError("Expected CSV at top level of S3 key")

        if len(key_parts) == 5:
            module = key_parts[1]
            filename = key_parts[4]
            form_name = filename.split('_')[1]
            if form_name == 'header':
                form_name = f'{module.lower()}_header'

            return ErrorCheckKey(full_path=key,
                                 csv=key_parts[0],
                                 module=module,
                                 form_ver=key_parts[2],
                                 packet=key_parts[3],
                                 filename=filename,
                                 form_name=form_name)
        elif len(key_parts) == 4:
            module = key_parts[1]
            assert module == 'ENROLL'
            filename = key_parts[3]
            form_name = 'enrl'
            return ErrorCheckKey(full_path=key,
                                 csv=key_parts[0],
                                 module=module,
                                 form_ver=key_parts[2],
                                 filename=filename,
                                 form_name=form_name)

        raise ValueError(
            f"Cannot parse ErrorCheckKey components from {key}; " +
            "Expected to be of the form " +
            "CSV / MODULE / FORM_VER / PACKET / filename")

    def get_visit_type(self) -> Optional[str]:
        """Determine visit type from packet.

        Returns:
            The visit type; None if there is no corresponding packet
        """
        if not self.packet:
            return None

        if self.packet == 'I4':
            return 'i4vp'

        return 'fvp' if self.packet.startswith('F') else 'ivp'


class ErrorCheckImportStats:
    """Class for keeping track of import stats."""

    def __init__(self):
        """Initializer."""
        self.__total_records = 0
        self.__all_error_codes = []
        self.__failed_files = []

    @property
    def total_records(self) -> int:
        """Returns the total records."""
        return self.__total_records

    @property
    def all_error_codes(self) -> List[str]:
        """Returns the list of failed files."""
        return self.__all_error_codes

    @property
    def failed_files(self) -> List[str]:
        """Returns the list of failed files."""
        return self.__failed_files

    def add_to_total_records(self, num_records: int) -> None:
        """Adds to the total records.

        Args:
            num_records: Amount to add
        """
        self.__total_records += num_records

    def add_failed_file(self, failed_file: str) -> None:
        """Adds to the failed files.

        Args:
            failed_file: The failed file.
        """
        self.__failed_files.append(failed_file)

    def add_error_codes(self, error_codes: List[str]) -> List[str]:
        """Adds the error codes and checks if there are duplicates. This class
        adds the duplicates regardless, that way we don't drop unrelated error
        codes. It is up to the caller to decide what to do about it.

        Args:
            error_codes: The error codes to add
        Returns:
            The list of duplicates, if any are found
        """
        duplicates = []
        for code in error_codes:
            if code in self.__all_error_codes:
                duplicates.append(code)

        self.__all_error_codes.extend(error_codes)
        return duplicates
