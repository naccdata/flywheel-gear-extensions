"""Defines utilities for writing data files."""

from abc import ABC, abstractmethod
from csv import QUOTE_MINIMAL, DictWriter
from io import StringIO
from typing import Any, Dict, List, Optional, TextIO

SimpleJSONObject = Dict[str, Optional[int | str | bool | float]]


# pylint: disable=(too-few-public-methods)
class CSVWriter:
    """Wrapper for DictWriter that ensures header is written."""

    def __init__(self, stream: TextIO, fieldnames: List[str]) -> None:
        self.__writer = DictWriter(stream,
                                   fieldnames=fieldnames,
                                   dialect='unix',
                                   quoting=QUOTE_MINIMAL)
        self.__header_written = False

    def __write_header(self):
        """Writes the header to the output stream."""
        if self.__header_written:
            return

        self.__writer.writeheader()
        self.__header_written = True

    def write(self, json_object: SimpleJSONObject) -> None:
        """Writes the dictionary to the stream.

        Dictionary is assumed to correspond to a row from a CSV file, and so
        the values all must have primitive types.

        Args:
          json_object: dictionary with only primitive values
        """
        self.__write_header()
        self.__writer.writerow(json_object)


# pylint: disable=(too-few-public-methods)
class JSONWriter(ABC):
    """Abstract base class for writing JSON objects."""

    @abstractmethod
    def write(self, dict_obj: Dict[str, Any]) -> None:
        """Writes the dictionary object as JSON.

        Args:
          object: the dictionary object
        """


class ListJSONWriter(JSONWriter):
    """Collects objects in a list."""

    def __init__(self) -> None:
        self.__objects: List[Dict[str, Any]] = []

    def write(self, dict_obj: Dict[str, Any]) -> None:
        """Captures object for writing to file.

        Args:
          object: a dictionary object
        """
        self.__objects.append(dict_obj)

    def object_list(self) -> List[Dict[str, Any]]:
        """Returns list of accumulated dict objects.

        Returns:
          List of dictionary objects
        """
        return self.__objects


def write_csv_to_stream(headers: List[str], data: List[Dict[str,
                                                            Any]]) -> StringIO:
    """Takes a header and data pair and uses CSVWriter to write the CSV
    contents to a StringIO stream.

    Args:
        headers: The header values
        data: The data values, expected to be a list of JSON dicts

    Returns:
        StringIO object containing the contents.
    """
    stream = StringIO()
    writer = CSVWriter(stream, headers)
    for row in data:
        writer.write(row)

    return stream
