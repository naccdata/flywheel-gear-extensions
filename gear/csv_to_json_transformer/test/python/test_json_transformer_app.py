import csv
from io import StringIO
from typing import Any, Dict, List

import pytest
from csv_app.main import CSVTransformVisitor
from inputs.csv_reader import read_csv
from outputs.errors import StreamErrorWriter
from transform.transformer import FieldTransformations, TransformerFactory


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


def empty(stream) -> bool:
    """Checks that the stream is empty.

    Returns   True if no data is read from the stream, False otherwise
    """
    stream.seek(0)
    return not bool(stream.readline())


@pytest.fixture(scope="module")
def missing_columns_table():
    yield [['dummy1', 'dummy2', 'dummy3'], [1, 1, 8], [1, 2, 99]]


@pytest.fixture(scope="function")
def missing_columns_stream(missing_columns_table):
    """Create data stream missing expected column headers."""
    data = missing_columns_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="module")
def valid_visit_table():
    yield [['module', 'formver', 'naccid', 'visitnum', 'dummyvar'],
           ['UDS', '4', 'NACC000000', '1', '888']]


@pytest.fixture(scope="function")
def visit_data_stream(valid_visit_table):
    """Create mock data stream."""
    data = valid_visit_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="module")
def valid_nonvisit_table():
    yield [['module', 'formver', 'naccid', 'visitdate', 'dummyvar'],
           ['NP', '11', 'NACC0000000', '2003-10-2', '888']]


@pytest.fixture(scope="function")
def nonvisit_data_stream(valid_nonvisit_table):
    """Data stream for valid non-visit.

    Non-visit has date instead of visit number
    """
    data = valid_nonvisit_table
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


class TestCSVTransformVisitor:
    """Tests csv-to-json transformation."""

    def test_missing_column_headers(self, missing_columns_stream):
        """test missing expected column headers."""
        err_stream = StringIO()
        records: Dict[str, List[Dict[str, Any]]] = {}
        error_writer = StreamErrorWriter(stream=err_stream,
                                         container_id='dummy',
                                         fw_path='dummy/dummy')
        visitor = CSVTransformVisitor(req_fields=['naccid'],
                                      transformed_records=records,
                                      error_writer=error_writer,
                                      transformer_factory=TransformerFactory(
                                          FieldTransformations()))

        errors = read_csv(input_file=missing_columns_stream,
                          error_writer=error_writer,
                          visitor=visitor)
        assert errors, ("expect error for missing columns")
        assert not empty(err_stream), "expect error message in output"

    def test_valid_visit(self, visit_data_stream):
        """Test case where data corresponds to form completed at visit."""
        err_stream = StringIO()
        records: Dict[str, List[Dict[str, Any]]] = {}
        error_writer = StreamErrorWriter(stream=err_stream,
                                         container_id='dummy',
                                         fw_path='dummy/dummy')
        visitor = CSVTransformVisitor(req_fields=['naccid'],
                                      transformed_records=records,
                                      error_writer=error_writer,
                                      transformer_factory=TransformerFactory(
                                          FieldTransformations()))
        errors = read_csv(input_file=visit_data_stream,
                          error_writer=error_writer,
                          visitor=visitor)
        assert not errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"

    def test_valid_nonvisit(self, nonvisit_data_stream):
        """Test case where data does not correspond to visit."""
        err_stream = StringIO()
        records: Dict[str, List[Dict[str, Any]]] = {}
        error_writer = StreamErrorWriter(stream=err_stream,
                                         container_id='dummy',
                                         fw_path='dummy/dummy')
        visitor = CSVTransformVisitor(req_fields=['naccid'],
                                      transformed_records=records,
                                      error_writer=error_writer,
                                      transformer_factory=TransformerFactory(
                                          FieldTransformations()))
        errors = read_csv(input_file=nonvisit_data_stream,
                          error_writer=error_writer,
                          visitor=visitor)

        assert not errors, "expect no errors"
        assert empty(err_stream), "expect error stream to be empty"
