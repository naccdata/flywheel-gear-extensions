"""Tests for the APOE transformer, namely APOETransformerCSVVisitor."""
import logging

import pytest
from apoe_transformer_app.main import (
    APOE_ENCODINGS,
    APOETransformerCSVVisitor,
)
from outputs.errors import ListHandler, LogErrorWriter


@pytest.fixture(scope='function')
def list_handler():
    """Creates a list handler for testing."""
    return ListHandler()


@pytest.fixture(scope='function')
def visitor(list_handler):
    """Creates a APOETransformerCSVVisitor for testing."""
    log = logging.getLogger(__name__)
    log.addHandler(list_handler)

    error_writer = LogErrorWriter(log)
    return APOETransformerCSVVisitor(error_writer)


@pytest.fixture(scope='module')
def apoe_headers():
    """Creates the expected headers."""
    return APOETransformerCSVVisitor.EXPECTED_INPUT_HEADERS


class TestAPOETransformerCSVVisitor:
    """Tests the APOETransformerCSVVisitor class."""

    def test_visit_header(self, visitor, apoe_headers):
        """Test the visit_header method."""
        assert visitor.visit_header(apoe_headers)
        assert visitor.visit_header((*apoe_headers, 'extra1', 'extra2'))
        assert visitor.visit_header(['ADCID', 'PTID', 'NACCID', 'A1', 'A2'])

    def test_visit_header_invalid(self, visitor, list_handler):
        """Test an invalid header."""
        assert not visitor.visit_header(['a2'])
        assert not visitor.visit_header([])

        errors = list_handler.get_logs()
        assert len(errors) == 3
        for error in errors:
            assert error['message'].startswith(
                'Missing one or more required field(s)')
            assert error['message'].endswith('in the header')

    def test_visit_row(self, visitor, apoe_headers):
        """Test the visit_row method, and check that the transformed_data
        property was updated."""
        visitor.visit_header(apoe_headers)
        for i, (pair, value) in enumerate(APOE_ENCODINGS.items()):
            data = {
                'adcid': 0,
                'ptid': 0,
                'naccid': 0,
                'a1': pair[0],
                'a2': pair[1]
            }
            assert visitor.visit_row(data, i + 1)
            assert len(visitor.transformed_data) == i + 1
            assert visitor.transformed_data[i] == {
                'adcid': 0,
                'ptid': 0,
                'naccid': 0,
                'apoe': value
            }

        # test the 9/unknown case
        data = {'adcid': 3, 'ptid': 3, 'naccid': 3, 'a1': "EE", 'a2': "FF"}
        assert visitor.visit_row(data, 10)
        assert len(visitor.transformed_data) == 10
        assert visitor.transformed_data[9] == {
            'adcid': 3,
            'ptid': 3,
            'naccid': 3,
            'apoe': 9
        }

    def test_visit_row_drops_extra_fields(self, visitor, apoe_headers):
        """Test that the visit_row method drops unexpected fields in output."""
        visitor.visit_header(apoe_headers)

        data = {
            'Adcid': 3,
            'Ptid': 3,
            'Naccid': 3,
            'A1': "EE",
            'A2': "FF",
            'extra1': 'hello',
            'extra2': 'world'
        }
        assert visitor.visit_row(data, 1)
        assert len(visitor.transformed_data) == 1
        assert visitor.transformed_data[0] == {
            'adcid': 3,
            'ptid': 3,
            'naccid': 3,
            'extra1': 'hello',
            'extra2': 'world',
            'apoe': 9
        }
