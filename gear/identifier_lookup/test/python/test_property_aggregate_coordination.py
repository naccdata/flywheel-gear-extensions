"""Property test for aggregate visitor coordination.

**Feature: identifier-lookup-refactoring, Property 4: Aggregate Visitor Coordination**
**Validates: Requirements 3.2, 3.3**
"""

import csv
from io import StringIO
from typing import Dict, List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from hypothesis import given, settings
from hypothesis import strategies as st
from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


@given(
    num_rows=st.integers(min_value=1, max_value=10),
    has_valid_identifiers=st.booleans(),
)
@settings(max_examples=100)
def test_aggregate_visitor_processes_all_rows(
    num_rows: int, has_valid_identifiers: bool
):
    """Property test: Aggregate visitor executes both visitors for each row.

    **Feature: identifier-lookup-refactoring, Property 4: Aggregate Visitor
    Coordination**
    **Validates: Requirements 3.2, 3.3**

    For any CSV file processing, the AggregateCSVVisitor should execute both
    identifier lookup and QC logging visitors for each row.
    """
    # Arrange - Generate test data
    ptids = [f"P{i:03d}" for i in range(num_rows)]

    # Create identifiers based on test parameter
    identifiers: Dict[str, IdentifierObject]
    if has_valid_identifiers:
        identifiers = {
            ptid: IdentifierObject(
                naccid=f"NACC{i:06d}",
                adcid=1,
                ptid=ptid,
                guid=None,
                naccadc=1000 + i,
            )
            for i, ptid in enumerate(ptids)
        }
    else:
        identifiers = {}

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create both visitors
    identifier_visitor = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    # Create aggregate visitor
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=visit_all_strategy
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

    rows_processed = 0
    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)
        rows_processed += 1

    # Assert - Verify both visitors were executed for all rows
    assert header_result, "Header validation should succeed for all visitors"
    assert rows_processed == num_rows, "All rows should be processed"

    # Verify QC visitor was called for each row
    assert mock_qc_creator.update_qc_log.call_count == num_rows, (
        f"QC visitor should be called for all {num_rows} rows"
    )

    # Verify identifier visitor processed all rows (output or errors)
    if has_valid_identifiers:
        output_stream.seek(0)
        output_reader = csv.DictReader(output_stream)
        output_rows = list(output_reader)
        assert len(output_rows) == num_rows, (
            "Identifier visitor should produce output for all valid identifiers"
        )
    else:
        # With invalid identifiers, no output should be produced
        output_stream.seek(0)
        output_content = output_stream.getvalue()
        lines = output_content.strip().split("\n") if output_content.strip() else []
        assert len(lines) <= 1, "No data rows should be written for invalid identifiers"


def test_aggregate_visitor_validates_all_headers():
    """Property test: Aggregate visitor ensures all visitors validate headers.

    **Feature: identifier-lookup-refactoring, Property 4: Aggregate Visitor
    Coordination**
    **Validates: Requirements 3.2, 3.3**

    For any CSV file processing, the AggregateCSVVisitor should ensure all
    constituent visitors validate the header successfully.
    """
    # Arrange - Create test data with valid header
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        )
    }

    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []
    output_stream = StringIO()

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    identifier_visitor = NACCIDLookupVisitor(
        adcid=1,
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=visit_all_strategy
    )

    # Act - Test with valid header
    valid_header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    valid_result = aggregate_visitor.visit_header(valid_header)

    # Assert - Valid header should pass
    assert valid_result, "Valid header should be accepted by all visitors"

    # Act - Test with invalid header (missing required fields)
    invalid_header = ["ptid", "visitdate"]  # Missing required fields
    invalid_result = aggregate_visitor.visit_header(invalid_header)

    # Assert - Invalid header should fail
    assert not invalid_result, (
        "Invalid header should be rejected when any visitor fails validation"
    )
