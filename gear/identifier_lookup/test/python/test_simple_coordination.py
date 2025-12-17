"""Simple test for visitor coordination mechanism."""

import csv
from io import StringIO
from typing import Dict, List

from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


def test_simple_coordination():
    """Simple test to verify basic coordination mechanism works."""
    # Arrange - Create test data with valid identifiers
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        ),
    }

    # Create shared error writer for coordination
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create visitor with shared error writer
    identifier_visitor = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Create CSV data
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = [
        {
            "adcid": 1,
            "ptid": "P001",
            "visitdate": "2024-01-01",
            "visitnum": "1",
            "packet": "I",
            "formver": "4.0",
        }
    ]

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Act - Process CSV with identifier visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = identifier_visitor.visit_header(header_list)

    row_result = True
    for line_num, row in enumerate(csv_reader, start=2):
        if not identifier_visitor.visit_row(row, line_num):
            row_result = False

    # Assert - Verify basic functionality works
    assert header_result, "Header processing should succeed"
    assert row_result, "Row processing should succeed"

    # Verify identifier lookup produced output
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == 1, "Should produce one output row"

    # Verify no errors in shared error writer for successful lookup
    errors = shared_error_writer.errors()
    assert len(errors.root) == 0, "Should have no errors for successful lookup"


def test_simple_coordination_with_failure():
    """Simple test to verify coordination mechanism handles failures."""
    # Arrange - Create test data with invalid identifiers (empty map)
    identifiers: Dict[str, IdentifierObject] = {}

    # Create shared error writer for coordination
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create visitor with shared error writer
    identifier_visitor = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Create CSV data with invalid PTID
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = [
        {
            "adcid": 1,
            "ptid": "INVALID",
            "visitdate": "2024-01-01",
            "visitnum": "1",
            "packet": "I",
            "formver": "4.0",
        }
    ]

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Act - Process CSV with identifier visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    identifier_visitor.visit_header(header_list)

    row_result = True
    for line_num, row in enumerate(csv_reader, start=2):
        if not identifier_visitor.visit_row(row, line_num):
            row_result = False

    # Assert - Verify failure handling works
    assert not row_result, "Row processing should fail for invalid PTID"

    # Verify no output was generated for failed lookup
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    lines = output_content.strip().split("\n") if output_content.strip() else []
    assert len(lines) <= 1, "No data rows should be written for failed lookup"

    # Verify errors were recorded in shared error writer
    errors = shared_error_writer.errors()
    assert len(errors.root) > 0, "Should have errors for failed lookup"
