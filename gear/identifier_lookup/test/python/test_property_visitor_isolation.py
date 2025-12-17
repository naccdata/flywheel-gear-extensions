"""Property test for visitor isolation mechanism.

**Feature: identifier-lookup-refactoring, Property 8: Visitor Isolation**
**Validates: Requirements 5.5**
"""

import csv
from io import StringIO
from typing import Any, Dict, List

from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import CSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


class FailingMockVisitor(CSVVisitor):
    """Mock visitor that always fails to test isolation."""

    def __init__(self):
        self.visit_header_called = False
        self.visit_row_called = False
        self.visit_row_call_count = 0

    def visit_header(self, header: List[str]) -> bool:
        """Mock header visit that succeeds."""
        self.visit_header_called = True
        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Mock row visit that always fails."""
        self.visit_row_called = True
        self.visit_row_call_count += 1
        # Simulate an error in this visitor
        raise RuntimeError(f"Mock visitor failure for row {line_num}")


class SucceedingMockVisitor(CSVVisitor):
    """Mock visitor that always succeeds to test isolation."""

    def __init__(self):
        self.visit_header_called = False
        self.visit_row_called = False
        self.visit_row_call_count = 0

    def visit_header(self, header: List[str]) -> bool:
        """Mock header visit that succeeds."""
        self.visit_header_called = True
        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Mock row visit that always succeeds."""
        self.visit_row_called = True
        self.visit_row_call_count += 1
        return True


def test_visitor_isolation_error_handling():
    """Property test: Visitor isolation handles errors gracefully.

    **Feature: identifier-lookup-refactoring, Property 8: Visitor Isolation**
    **Validates: Requirements 5.5**

    For any error occurring in one visitor, the system should handle the failure
    gracefully without corrupting the other visitor's state.
    """
    # Arrange - Create test data with valid identifiers
    ptids = ["P001", "P002"]
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        ),
        "P002": IdentifierObject(
            naccid="NACC000002", adcid=1, ptid="P002", guid=None, naccadc=1002
        ),
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create real identifier visitor
    identifier_visitor = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Create mock visitors - one that fails, one that succeeds
    failing_visitor = FailingMockVisitor()
    succeeding_visitor = SucceedingMockVisitor()

    # Import and create aggregate visitor with non-short-circuiting behavior
    from inputs.csv_reader import AggregateCSVVisitor

    # Test with failing visitor first, then succeeding visitor
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, failing_visitor, succeeding_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Create CSV data
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in ptids:
        rows.append(
            {
                "adcid": 1,
                "ptid": ptid,
                "visitdate": "2024-01-01",
                "visitnum": "1",
                "packet": "I",
                "formver": "4.0",
            }
        )

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Act - Process CSV with aggregate visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = aggregate_visitor.visit_header(header_list)

    # Process rows and expect failures due to failing visitor
    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify isolation worked correctly
    assert header_result, "Header processing should succeed"
    assert failed_rows == len(ptids), "All rows should fail due to failing visitor"

    # Verify that the identifier visitor still processed successfully
    # (its state should not be corrupted by the failing visitor)
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), (
        "Identifier visitor should still produce output despite other visitor failing"
    )

    # Verify all visitors were called despite failures
    assert failing_visitor.visit_header_called, (
        "Failing visitor should be called for header"
    )
    assert failing_visitor.visit_row_called, "Failing visitor should be called for rows"
    assert failing_visitor.visit_row_call_count == len(ptids), (
        "Failing visitor should be called for all rows"
    )

    assert succeeding_visitor.visit_header_called, (
        "Succeeding visitor should be called for header"
    )
    assert succeeding_visitor.visit_row_called, (
        "Succeeding visitor should be called for rows"
    )
    assert succeeding_visitor.visit_row_call_count == len(ptids), (
        "Succeeding visitor should be called for all rows"
    )

    # Verify identifier visitor state is intact
    for i, output_row in enumerate(output_rows):
        expected_ptid = ptids[i]
        expected_naccid = identifiers[expected_ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            "Identifier lookup should work correctly despite other visitor failures"
        )


def test_visitor_isolation_state_independence():
    """Property test: Visitor state independence.

    **Feature: identifier-lookup-refactoring, Property 8: Visitor Isolation**
    **Validates: Requirements 5.5**

    For any processing scenario, each visitor should maintain its own state
    independently without interference from other visitors.
    """
    # Arrange - Create test data
    ptids = ["P001", "P002", "P003"]
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        ),
        "P002": IdentifierObject(
            naccid="NACC000002", adcid=1, ptid="P002", guid=None, naccadc=1002
        ),
        "P003": IdentifierObject(
            naccid="NACC000003", adcid=1, ptid="P003", guid=None, naccadc=1003
        ),
    }

    # Create separate error writers for each visitor to test isolation
    error_writer_1 = ListErrorWriter(container_id="test1", fw_path="test-path-1")
    error_writer_2 = ListErrorWriter(container_id="test2", fw_path="test-path-2")

    misc_errors_1: List[FileError] = []
    misc_errors_2: List[FileError] = []

    # Create separate output streams
    output_stream_1 = StringIO()
    output_stream_2 = StringIO()

    # Create two separate identifier visitors with different configurations
    visitor_1 = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream_1,
        module_name="test1",
        module_configs=uds_ingest_configs(),
        error_writer=error_writer_1,
        misc_errors=misc_errors_1,
    )

    visitor_2 = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream_2,
        module_name="test2",
        module_configs=uds_ingest_configs(),
        error_writer=error_writer_2,
        misc_errors=misc_errors_2,
    )

    # Import and create aggregate visitor with non-short-circuiting behavior
    from inputs.csv_reader import AggregateCSVVisitor

    aggregate_visitor = AggregateCSVVisitor(
        [visitor_1, visitor_2], strategy_builder=visit_all_strategy
    )

    # Create CSV data
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in ptids:
        rows.append(
            {
                "adcid": 1,
                "ptid": ptid,
                "visitdate": "2024-01-01",
                "visitnum": "1",
                "packet": "I",
                "formver": "4.0",
            }
        )

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Act - Process CSV with aggregate visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = aggregate_visitor.visit_header(header_list)

    all_rows_processed = True
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            all_rows_processed = False

    # Assert - Verify state independence
    assert header_result, "Header processing should succeed"
    assert all_rows_processed, "All rows should be processed successfully"

    # Verify each visitor maintained independent state
    # Check output stream 1
    output_stream_1.seek(0)
    output_reader_1 = csv.DictReader(output_stream_1)
    output_rows_1 = list(output_reader_1)
    assert len(output_rows_1) == len(ptids), "Visitor 1 should produce all output rows"

    # Check output stream 2
    output_stream_2.seek(0)
    output_reader_2 = csv.DictReader(output_stream_2)
    output_rows_2 = list(output_reader_2)
    assert len(output_rows_2) == len(ptids), "Visitor 2 should produce all output rows"

    # Verify each visitor used its own module name
    for output_row in output_rows_1:
        assert output_row["module"] == "test1", (
            "Visitor 1 should use its own module name"
        )

    for output_row in output_rows_2:
        assert output_row["module"] == "test2", (
            "Visitor 2 should use its own module name"
        )

    # Verify error writers remained independent
    # (both should be empty for successful processing)
    errors_1 = error_writer_1.errors()
    errors_2 = error_writer_2.errors()
    assert len(errors_1.root) == 0, "Visitor 1 should have no errors"
    assert len(errors_2.root) == 0, "Visitor 2 should have no errors"

    # Verify misc_errors lists remained independent
    assert len(misc_errors_1) == 0, "Visitor 1 misc errors should be empty"
    assert len(misc_errors_2) == 0, "Visitor 2 misc errors should be empty"
    assert misc_errors_1 is not misc_errors_2, (
        "Misc errors lists should be separate objects"
    )
