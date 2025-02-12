"""Defines the APOE Transformer."""
import logging
from typing import Any, Dict, List, TextIO, Tuple

from flywheel import FileSpec
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import (
    LogErrorWriter,
    missing_field_error,
)
from outputs.outputs import write_csv_to_stream

log = logging.getLogger(__name__)

# NCRAD (a1, a2) to NACC encoding
APOE_ENCODINGS: Dict[Tuple[str, str], int] = {
    ("E3", "E3"): 1,
    ("E3", "E4"): 2,
    ("E4", "E3"): 2,
    ("E3", "E2"): 3,
    ("E2", "E3"): 3,
    ("E4", "E4"): 4,
    ("E4", "E2"): 5,
    ("E2", "E4"): 5,
    ("E2", "E2"): 6
}


class APOETransformerCSVVisitor(CSVVisitor):
    """Class for visiting each row in the APOE genotype CSV."""

    EXPECTED_INPUT_HEADERS: Tuple[str, ...] = ('a1', 'a2')

    def __init__(self, error_writer: LogErrorWriter):
        """Initializer."""
        self.__error_writer: LogErrorWriter = error_writer
        self.__transformed_data: List[Dict[Any, Any]] = []
        self.__header: List[str] = []

    @property
    def transformed_data(self):
        """The APOE transformed data."""
        return self.__transformed_data

    @property
    def header(self) -> List[str]:
        """Returns the output header."""
        return self.__header

    def visit_header(self, header: List[str]) -> bool:
        """Verifies that the header is valid.

        Args:
            header: The list of headers from the input CSV
        Returns:
            True if the header is valid, else False
        """
        header = [x.strip().lower() for x in header]
        missing = set(self.EXPECTED_INPUT_HEADERS) - set(header)
        for field in missing:
            error = missing_field_error(field)
            self.__error_writer.write(error)

        if missing:
            return False

        self.__header = [
            column for column in header if column not in ['a1', 'a2']
        ]
        self.__header.append('apoe')

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for the row (per DictReader) and perform the
        APOE transformation.

        Args:
            row: The row data
            line_num: The line number of the row
        Returns:
            True if the row is valid and transformed successfully, else False
        """
        row = {k.strip().lower(): v for k, v in row.items()}
        a1, a2 = row.pop('a1'), row.pop('a2')
        pair = (a1.strip().upper(), a2.strip().upper())
        row['apoe'] = APOE_ENCODINGS.get(pair, 9)

        self.__transformed_data.append(row)
        return True


def run(*,
        proxy: FlywheelProxy,
        input_file: TextIO,
        filename: str,
        project: ProjectAdaptor,
        delimiter: str = ','):
    """Runs the APOE transformation process.

    Args:
        proxy: the proxy for the Flywheel instance
        input_file: The input CSV TextIO stream to transform on
        filename: The output filename to write to
        project: The target project to upload results to
        delimiter: The input CSV delimiter
    """
    # read the CSV
    error_writer = LogErrorWriter(log)
    visitor = APOETransformerCSVVisitor(error_writer)
    success = read_csv(input_file=input_file,
                       error_writer=error_writer,
                       visitor=visitor,
                       delimiter=delimiter)

    if not success:
        raise GearExecutionError(
            'Errors found while reading the input CSV file')

    # write transformed results to target project
    log.info(f"Writing transformed APOE data to {project.id}")
    contents = write_csv_to_stream(headers=visitor.header,
                                   data=visitor.transformed_data).getvalue()
    file_spec = FileSpec(name=filename,
                         contents=contents,
                         content_type='text/csv',
                         size=len(contents))

    if proxy.dry_run:
        log.info(f"DRY RUN: Would have uploaded {filename}")
    else:
        project.upload_file(file_spec)  # type: ignore
        log.info(f"Successfully uploaded {filename}")
