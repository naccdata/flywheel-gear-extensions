"""Tests for the identifier_app.main.run."""
import csv
from io import StringIO
from typing import Any, List

import pytest
from identifier_app.main import NACCIDLookupVisitor, run
from identifiers.model import IdentifierObject
from outputs.errors import ListErrorWriter


@pytest.fixture(scope="function")
def empty_data_stream():
    """Create empty data stream."""
    yield StringIO()


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


@pytest.fixture(scope="function")
def no_header_stream():
    """Create data stream without header row."""
    data = [[1, 1, 8], [1, 2, 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="function")
def no_ids_stream():
    """Create data stream without expected column headers."""
    data: List[List[str | int]] = [['dummy1', 'dummy2', 'dummy3'], [1, 1, 8],
                                   [1, 2, 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    yield stream


@pytest.fixture(scope="function")
def data_stream():
    """Create valid data stream with header row."""
    data: List[List[str | int]] = [['adcid', 'ptid', 'visitdate', 'var1'],
                                   [1, '1', '2024-12-31', 8],
                                   [1, '2', '2024-12-31', 99]]
    stream = StringIO()
    write_to_stream(data, stream)
    stream.seek(0)
    yield stream


@pytest.fixture(scope="function")
def identifiers_map():
    """Create identifiers map with IDs matching data stream."""
    id_map = {}
    id_map['1'] = IdentifierObject(naccid='NACC000001',
                                   adcid=1,
                                   ptid='1',
                                   guid=None,
                                   naccadc=1111)
    id_map['2'] = IdentifierObject(naccid='NACC000002',
                                   adcid=1,
                                   ptid='2',
                                   guid=None,
                                   naccadc=2222)
    yield id_map


@pytest.fixture(scope="function")
def mismatched_identifiers_map():
    """Create identifiers map with IDs that don't match data stream."""
    id_map = {}
    id_map['3'] = IdentifierObject(naccid='NACC000001',
                                   adcid=1,
                                   ptid='3',
                                   guid=None,
                                   naccadc=3333)
    id_map['4'] = IdentifierObject(naccid='NACC000002',
                                   adcid=1,
                                   ptid='4',
                                   guid=None,
                                   naccadc=4444)
    yield id_map


def empty(stream) -> bool:
    """Checks that the stream is empty.

    Returns   True if no data is read from the stream, False otherwise
    """
    stream.seek(0)
    return not bool(stream.readline())


# pylint: disable=no-self-use,redefined-outer-name
class TestIdentifierLookup:
    """Tests for the identifier-lookup-gear app."""

    def test_empty_input_stream(self, empty_data_stream: StringIO,
                                identifiers_map: dict[Any, Any]):
        """Test empty input stream."""
        out_stream = StringIO()
        error_writer = ListErrorWriter(container_id='dummy',
                                       fw_path='dummy-path')
        success = run(input_file=empty_data_stream,
                      lookup_visitor=NACCIDLookupVisitor(
                          adcid=1,
                          identifiers=identifiers_map,
                          output_file=out_stream,
                          module_name='dummy-module',
                          error_writer=error_writer,
                          date_field='visitdate',
                          gear_name='dummy'),
                      error_writer=error_writer)
        assert not success
        assert empty(out_stream)
        assert error_writer.errors()

    def test_no_header(self, no_header_stream: StringIO,
                       identifiers_map: dict[Any, Any]):
        """Test case with no header."""
        out_stream = StringIO()
        error_writer = ListErrorWriter(container_id='dummy',
                                       fw_path='dummy-path')
        success = run(input_file=no_header_stream,
                      lookup_visitor=NACCIDLookupVisitor(
                          adcid=1,
                          identifiers=identifiers_map,
                          output_file=out_stream,
                          module_name='dummy-module',
                          error_writer=error_writer,
                          date_field='visitdate',
                          gear_name='dummy'),
                      error_writer=error_writer)
        assert not success
        assert empty(out_stream)
        assert error_writer.errors()

    def test_no_id_column_headers(self, no_ids_stream: StringIO,
                                  identifiers_map: dict[Any, Any]):
        """Test case where header doesn't have ID columns."""
        out_stream = StringIO()
        error_writer = ListErrorWriter(container_id='dummy',
                                       fw_path='dummy-path')
        success = run(input_file=no_ids_stream,
                      lookup_visitor=NACCIDLookupVisitor(
                          adcid=1,
                          identifiers=identifiers_map,
                          output_file=out_stream,
                          module_name='dummy-module',
                          error_writer=error_writer,
                          date_field='visitdate',
                          gear_name='dummy'),
                      error_writer=error_writer)
        assert not success
        assert empty(out_stream)
        assert error_writer.errors()

    def test_data_with_matching_ids(self, data_stream: StringIO,
                                    identifiers_map: dict[Any, Any]):
        """Test case where everything should match."""
        out_stream = StringIO()
        error_writer = ListErrorWriter(container_id='dummy',
                                       fw_path='dummy-path')
        success = run(input_file=data_stream,
                      lookup_visitor=NACCIDLookupVisitor(
                          adcid=1,
                          identifiers=identifiers_map,
                          output_file=out_stream,
                          module_name='dummy-module',
                          error_writer=error_writer,
                          date_field='visitdate',
                          gear_name='dummy'),
                      error_writer=error_writer)
        assert success
        assert not error_writer.errors()
        assert not empty(out_stream)
        out_stream.seek(0)
        reader = csv.DictReader(out_stream, dialect='unix')
        assert reader.fieldnames
        assert 'naccid' in reader.fieldnames
        row = next(reader)
        assert row['naccid'] == 'NACC000001'
        row = next(reader)
        assert row['naccid'] == 'NACC000002'

    def test_data_with_mismatched_ids(self, data_stream: StringIO,
                                      mismatched_identifiers_map: dict[Any,
                                                                       Any]):
        """Test case where there is no matching identifier."""
        out_stream = StringIO()
        error_writer = ListErrorWriter(container_id='dummy',
                                       fw_path='dummy-path')
        success = run(input_file=data_stream,
                      lookup_visitor=NACCIDLookupVisitor(
                          identifiers=mismatched_identifiers_map,
                          adcid=1,
                          output_file=out_stream,
                          module_name='dummy-module',
                          error_writer=error_writer,
                          date_field='visitdate',
                          gear_name='dummy'),
                      error_writer=error_writer)
        assert not success
        assert empty(out_stream)
        assert error_writer.errors()
