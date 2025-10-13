"""Defines Gather Form Data."""

import logging
from typing import TextIO

from data_requests.data_request import (
    DataRequestVisitor,
)
from inputs.csv_reader import read_csv
from outputs.error_writer import ErrorWriter

log = logging.getLogger(__name__)


def run(
    *,
    request_file: TextIO,
    request_visitor: DataRequestVisitor,
    error_writer: ErrorWriter,
):
    """Runs the Gather Form Data process, which reads individual participant
    request from the request file, applies the visitor to each to gather data
    for each form module.

    The error writer collects errors/warnings encountered while reading the request file.

    Args:
        request_file: the data request file
        request_visitor: the visitor
        error_writer: the error writer
    """
    return read_csv(
        input_file=request_file,
        error_writer=error_writer,
        visitor=request_visitor,
    )
