"""Tests for CSV Center Splitter, namely the CSVCenterSplitterVisitor."""
import pytest
from csv_center_splitter_app.main import CSVVisitorCenterSplitter
from outputs.errors import ListErrorWriter


@pytest.fixture(scope='function')
def error_writer():
    """Creates an ErrorWriter for testing."""
    return ListErrorWriter(container_id='dummmy-container',
                           fw_path='dummy-fw-path')


@pytest.fixture(scope='function')
def visitor(error_writer):
    """Creates a CSVVisitorCenterSplitter for testing."""
    visitor = CSVVisitorCenterSplitter('adcid', error_writer)
    assert visitor.visit_header(['adcid', 'data'])
    return visitor


@pytest.fixture(scope='module')
def merged_csv_data():
    """Creates dummy CSV data with merged cells."""
    return [
        {'adcid': '1', 'data': 'dummy_value', 'extra': ''},
        {'adcid': '', 'data': 'dummy_value_2', 'extra': ''},
        {'adcid': '', 'data': '', 'extra': ''},
        {'adcid': '2', 'data': 'hello', 'extra': ''},
        {'adcid': '', 'data': 'world', 'extra': ''}
    ]


class TestCSVVisitorCenterSplitter:
    """Tests the CSVVisitorCenterSplitter class."""

    def test_visit_header(self, visitor):
        """Test the visit_header method, also checks that headers property is
        updated."""
        assert visitor.headers == ['adcid', 'data']
        assert visitor.visit_header(['adcid'])
        assert visitor.headers == ['adcid']

    def test_visit_header_invalid(self, visitor):
        """Test an invalid header."""
        assert not visitor.visit_header(['id', 'data'])
        assert not visitor.visit_header([])

        errors = visitor.error_writer.errors()
        assert len(errors) == 2
        assert errors[0]['message'] == 'Missing field "adcid" in the header'

    def test_visit_row(self, visitor):
        """Test the visit_row method, also checks that split_data property is
        updated."""
        for i in range(10):
            data = {'adcid': '0', 'data': f'value{i}'}
            assert visitor.visit_row(data, i + 1)
            assert len(visitor.split_data["0"]) == i + 1
            assert visitor.split_data["0"][i] == data

        assert len(visitor.split_data) == 1

        data = {'adcid': '1', 'data': 'dummy_value'}
        assert visitor.visit_row(data, 11)
        assert len(visitor.split_data) == 2
        assert len(visitor.split_data["1"]) == 1
        assert visitor.split_data["1"][0] == data

    def test_visit_row_merged_allowed(self, error_writer, merged_csv_data):
        """Test when the CSV had merged cells."""
        visitor = CSVVisitorCenterSplitter('adcid',
                                           error_writer,
                                           allow_merged_cells=True)
        assert visitor.visit_header(['adcid', 'data', 'extra'])

        for i, row in enumerate(merged_csv_data):
            assert visitor.visit_row(row, i)

        split_data = visitor.split_data
        assert len(split_data) == 2
        assert split_data["1"] == merged_csv_data[0:3]
        assert split_data["2"] == merged_csv_data[3:5]

    def test_visit_row_merged_not_allowed(self, visitor, merged_csv_data):
        """Test when the CSV has merged cells but isn't allowed."""
        assert visitor.visit_row(merged_csv_data[0], 0)
        assert not visitor.visit_row(merged_csv_data[1], 1)

        errors = visitor.error_writer.errors()
        assert len(errors) == 1
        assert errors[0]['message'] == "Row 1 was invalid: Missing ADCID value"
