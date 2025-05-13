"""Module for formatting CSV file."""

from typing import Any, Dict, List, Optional, TextIO

from inputs.csv_reader import CSVVisitor
from keys.keys import REDCapKeys
from outputs.outputs import CSVWriter


class CSVFormatterVisitor(CSVVisitor):
    """This class formats the input CSV."""

    def __init__(self, *, output_stream: TextIO) -> None:
        self.__out_stream = output_stream
        self.__header: Optional[List[str]] = None
        self.__writer: Optional[CSVWriter] = None

    def __get_writer(self) -> CSVWriter:
        """Returns the writer for the CSV output.

        Manages whether writer has been initialized. Requires that
        header has been set.
        """
        if not self.__writer:
            assert self.__header, "Header must be set before visiting any rows"
            self.__writer = CSVWriter(stream=self.__out_stream,
                                      fieldnames=self.__header)

        return self.__writer

    def visit_header(self, header: List[str]) -> bool:
        """Convert the header to lowercase. Remove any REDCap specific columns
        form the header.

        Args:
          header: the list of header names

        Returns:
          True
        """
        self.__header = [column.strip().lower() for column in header]

        for key in REDCapKeys:
            if key in self.__header:
                self.__header.remove(key)

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Remove any REDCap specific columns form the row.

        Args:
          header: the list of header names

        Returns:
          True
        """

        out_row = {
            key.strip().lower(): value
            for key, value in row.items() if key.lower() not in REDCapKeys
        }

        writer = self.__get_writer()
        writer.write(out_row)

        return True
