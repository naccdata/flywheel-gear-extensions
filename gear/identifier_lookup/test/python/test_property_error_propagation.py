"""Property test for error propagation in aggregate visitor.

**Feature: identifier-lookup-refactoring,
  Property 5: Error Propagation**
**Validates: Requirements 3.4, 3.5**
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
from inputs.csv_reader import (
    AggregateCSVVisitor,
    short_circuit_strategy,
    visit_all_strategy,
)
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_identifiers_lambda_repository import (
    MockIdentifiersLambdaRepository,
)


@given(
    num_valid=st.integers(min_value=0, max_value=5),
    num_invalid=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100)
def test_error_propagation_with_failures(num_valid: int, num_invalid: int):
    """Property test: Error propagation when visitor failures occur.

      **Feature: identifier-lookup-refactoring,
    Property 5: Error Propagation**
      **Validates: Requirements 3.4, 3.5**

      For any visitor failure within the aggregate, the system should report
      the failure appropriately while maintaining correct processing order.
    """
    # Arrange - Create mix of valid and invalid PTIDs
    valid_ptids = [f"VALID{i:03d}" for i in range(num_valid)]
    invalid_ptids = [f"INVALID{i:03d}" for i in range(num_invalid)]
    all_ptids = valid_ptids + invalid_ptids

    # Create identifiers only for valid PTIDs
    identifiers: Dict[str, IdentifierObject] = {
        ptid: IdentifierObject(
            naccid=f"NACC{i:06d}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )
        for i, ptid in enumerate(valid_ptids)
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create both visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Create aggregate visitor with visit_all_strategy to continue on failures
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=visit_all_strategy
    )

    # Create CSV data
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in all_ptids:
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
    aggregate_visitor.visit_header(header_list)

    success_count = 0
    failure_count = 0
    for line_num, row in enumerate(csv_reader, start=2):
        result = aggregate_visitor.visit_row(row, line_num)
        if result:
            success_count += 1
        else:
            failure_count += 1

    # Assert - Verify error propagation
    total_rows = num_valid + num_invalid
    assert success_count + failure_count == total_rows, (
        "All rows should be processed (success or failure)"
    )

    # Verify failures are reported appropriately
    assert failure_count == num_invalid, (
        f"Expected {num_invalid} failures, got {failure_count}"
    )

    # Verify QC visitor was called for all rows (both success and failure)
    assert mock_qc_creator.update_qc_log.call_count == total_rows, (
        "QC visitor should be called for all rows, even failed ones"
    )

    # Verify correct processing order: valid rows produce output
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == num_valid, (
        f"Only valid identifiers should produce output: "
        f"expected {num_valid}, got {len(output_rows)}"
    )

    # Verify QC status reflects failures correctly
    qc_calls = mock_qc_creator.update_qc_log.call_args_list
    pass_count = sum(1 for call in qc_calls if call[1]["status"] == "PASS")
    fail_count = sum(1 for call in qc_calls if call[1]["status"] == "FAIL")

    assert pass_count == num_valid, (
        f"Expected {num_valid} PASS statuses, got {pass_count}"
    )
    assert fail_count == num_invalid, (
        f"Expected {num_invalid} FAIL statuses, got {fail_count}"
    )


def test_error_propagation_maintains_processing_order():
    """Property test: Processing order is maintained despite failures.

      **Feature: identifier-lookup-refactoring,
    Property 5: Error Propagation**
      **Validates: Requirements 3.4, 3.5**

      For any visitor failure within the aggregate, the system should maintain
      correct processing order (identifier lookup before QC logging).
    """
    # Arrange - Create test data with one invalid PTID
    ptids = ["VALID001", "INVALID", "VALID002"]
    identifiers = {
        "VALID001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="VALID001", guid=None, naccadc=1001
        ),
        "VALID002": IdentifierObject(
            naccid="NACC000002", adcid=1, ptid="VALID002", guid=None, naccadc=1002
        ),
    }

    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    output_stream = StringIO()

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Create aggregate visitor with visit_all_strategy
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
    aggregate_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)

    # Assert - Verify processing order is maintained
    # Check that QC visitor processed visits in the same order as input
    processed_visits = qc_visitor.get_processed_visits()
    assert len(processed_visits) == len(ptids), "All visits should be processed"

    for i, visit in enumerate(processed_visits):
        expected_ptid = ptids[i]
        assert visit.ptid == expected_ptid, (
            f"Processing order not maintained: "
            f"expected {expected_ptid} at position {i}, got {visit.ptid}"
        )

    # Verify QC calls were made in order
    qc_calls = mock_qc_creator.update_qc_log.call_args_list
    assert len(qc_calls) == len(ptids), "QC should be called for all rows in order"

    for i, call in enumerate(qc_calls):
        visit_keys = call[1]["visit_keys"]
        expected_ptid = ptids[i]
        assert visit_keys.ptid == expected_ptid, (
            f"QC call order not maintained: "
            f"expected {expected_ptid} at position {i}, got {visit_keys.ptid}"
        )


def test_short_circuit_strategy_stops_on_first_failure():
    """Property test: Short-circuit strategy stops on first failure.

      **Feature: identifier-lookup-refactoring,
    Property 5: Error Propagation**
      **Validates: Requirements 3.4, 3.5**

      When using short_circuit_strategy, the aggregate visitor should stop
      processing visitors after the first failure.
    """
    # Arrange - Create test data with invalid PTID
    identifiers: Dict[str, IdentifierObject] = {}  # Empty to cause failure

    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    output_stream = StringIO()

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="test",
    )

    # Create aggregate visitor with short_circuit_strategy
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=short_circuit_strategy
    )

    # Create CSV data with invalid PTID
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    row = {
        "adcid": 1,
        "ptid": "INVALID",
        "visitdate": "2024-01-01",
        "visitnum": "1",
        "packet": "I",
        "formver": "4.0",
    }

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerow(row)
    input_stream.seek(0)

    # Act - Process CSV with aggregate visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    aggregate_visitor.visit_header(header_list)

    for line_num, csv_row in enumerate(csv_reader, start=2):
        result = aggregate_visitor.visit_row(csv_row, line_num)
        assert not result, "Row processing should fail for invalid PTID"

    # Assert - Verify short-circuit behavior
    # With short_circuit_strategy, QC visitor should NOT be called
    # because identifier visitor fails first
    assert mock_qc_creator.update_qc_log.call_count == 0, (
        "QC visitor should not be called when short-circuit strategy "
        "stops on first failure"
    )
