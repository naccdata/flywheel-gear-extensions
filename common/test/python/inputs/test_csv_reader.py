"""Tests for CSV reader utilities."""
import csv
from io import StringIO
from typing import Any, Dict, List

import pytest
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import StreamErrorWriter, invalid_header_error


# pylint: disable=(redefined-outer-name)
@pytest.fixture(scope="function")
def empty_data_stream():
    """Create empty data stream."""
    yield StringIO()


# pylint: disable=(duplicate-code)
def write_to_stream(data: List[List[Any]], stream: StringIO) -> None:
    """Writes data to the StringIO object for use in a test.

    Resets stream pointer to beginning.

    Args:
      data: tabular data
      stream: the output stream
    """
    writer = csv.writer(stream,
                        delimiter=',',
                        quotechar='\"',
                        quoting=csv.QUOTE_NONNUMERIC,
                        lineterminator='\n')
    writer.writerows(data)
    stream.seek(0)


# pylint: disable=(redefined-outer-name)
@pytest.fixture(scope="function")
def no_header_stream():
    """Create data stream without header row."""
    data = [[1, 1, 8], [1, 2, 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


# pylint: disable=(redefined-outer-name)
@pytest.fixture(scope="function")
def no_ids_stream():
    """Create data stream without expected column headers."""
    data: List[List[str | int]] = [['dummy1', 'dummy2', 'dummy3'], [1, 1, 8],
                                   [1, 2, 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


# pylint: disable=(redefined-outer-name)
@pytest.fixture(scope="function")
def data_stream():
    """Create data stream without header row."""
    data: List[List[str | int]] = [['adcid', 'ptid', 'var1'], [1, '1', 8],
                                   [1, '2', 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    stream.seek(0)
    yield stream


def empty(stream) -> bool:
    """Checks that the stream is empty.

    Returns   True if no data is read from the stream, False otherwise
    """
    stream.seek(0)
    return not bool(stream.readline())


class DummyVisitor(CSVVisitor):
    """Dummy CSV Visitor class for testing."""

    def visit_header(self, header: List[str]) -> bool:
        return header is not None

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        return row is not None


class NonNumericHeaderVisitor(CSVVisitor):
    """Dummy CSV Visitor class for testing, which explicitly says the header
    cannot be numeric."""

    def __init__(self, error_writer: StreamErrorWriter):
        """Initializer."""
        self.__error_writer = error_writer

    def visit_header(self, header: List[str]) -> bool:
        """Visit header - cannot contain numeric values."""

        for x in header:
            try:
                float(x)
            except ValueError:
                continue

            error = invalid_header_error(message="Header cannot be numeric")
            self.__error_writer.write(error)
            return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        return row is not None


# pylint: disable=(no-self-use,too-few-public-methods)
class TestCSVReader:
    """Test class for csv reader."""

    def test_empty_input_stream(self, empty_data_stream):
        """Test empty input stream."""
        err_stream = StringIO()
        success = read_csv(input_file=empty_data_stream,
                           error_writer=StreamErrorWriter(
                               stream=err_stream,
                               container_id='dummy',
                               fw_path='dummy-path'),
                           visitor=DummyVisitor())
        assert not success
        assert not empty(err_stream)
        err_stream.seek(0)
        reader = csv.DictReader(err_stream, dialect='unix')
        assert reader.fieldnames
        row = next(reader)
        assert row['message'] == 'Empty input file'

    def test_invalid_header_stream(self, no_header_stream):
        """Test stream with invalid header row."""
        err_stream = StringIO()
        error_writer = StreamErrorWriter(stream=err_stream,
                                         container_id='dummy',
                                         fw_path='dummy-path')
        visitor = NonNumericHeaderVisitor(error_writer)

        success = read_csv(input_file=no_header_stream,
                           error_writer=error_writer,
                           visitor=visitor)
        assert not success
        assert not empty(err_stream)
        err_stream.seek(0)
        reader = csv.DictReader(err_stream, dialect='unix')
        assert reader.fieldnames
        row = next(reader)
        assert row['message'] == 'Header cannot be numeric'
