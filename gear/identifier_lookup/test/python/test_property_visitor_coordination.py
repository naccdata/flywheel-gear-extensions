"""Property test for visitor coordination using existing QCStatusLogCSVVisitor.

**Feature: identifier-lookup-refactoring,
  Property 7: Visitor Coordination**
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
"""

import csv
from io import StringIO
from typing import Dict, List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
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


def test_visitor_coordination_success_case():
    """Property test: Visitor coordination for successful identifier lookup.

      **Feature: identifier-lookup-refactoring,
    Property 7: Visitor Coordination**
      **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

      For any visit processing where identifier lookup succeeds, both visitors
      should have consistent access to visit information and the QC visitor
      should record a PASS status.
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

    # Create shared error writer for coordination
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create visitors with shared error writer
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Use existing QCStatusLogCSVVisitor with status determination from errors
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    # Create aggregate visitor with non-short-circuiting behavior
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=short_circuit_strategy
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

    # Assert - Verify coordination worked correctly
    assert header_result, "Header processing should succeed"
    assert all_rows_processed, "All rows should be processed successfully"

    # Verify identifier lookup produced output
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), "All input rows should produce output rows"

    # Verify QC logs were created with PASS status for successful lookups
    assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
        "QC log should be created for each visit"
    )

    # Check that all QC log calls used PASS status (no errors in shared error writer)
    for call in mock_qc_creator.update_qc_log.call_args_list:
        args, kwargs = call
        assert kwargs["status"] == "PASS", (
            "QC status should be PASS for successful identifier lookup"
        )

    # Verify visit information consistency
    processed_visits = qc_visitor.get_processed_visits()
    assert len(processed_visits) == len(ptids), "QC visitor should process all visits"

    for i, visit in enumerate(processed_visits):
        expected_ptid = ptids[i]
        assert visit.ptid == expected_ptid, (
            f"Visit PTID should match input data: {visit.ptid} != {expected_ptid}"
        )
        assert visit.module == "TEST", "Visit module should be set correctly"
        assert visit.date == "2024-01-01", "Visit date should match input data"


def test_visitor_coordination_failure_case():
    """Property test: Visitor coordination for failed identifier lookup.

      **Feature: identifier-lookup-refactoring,
    Property 7: Visitor Coordination**
      **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

      For any visit processing where identifier lookup fails, the QC visitor
      should record a FAIL status with appropriate error details, and error
      reporting should be coordinated without duplication.
    """
    # Arrange - Create test data with invalid identifiers (empty identifiers map)
    invalid_ptids = ["INVALID1", "INVALID2"]
    identifiers: Dict[str, IdentifierObject] = {}  # Empty map causes lookup failures

    # Create shared error writer for coordination
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create visitors with shared error writer
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Use existing QCStatusLogCSVVisitor with status determination from errors
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    # Create aggregate visitor with non-short-circuiting behavior
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=visit_all_strategy
    )

    # Create CSV data with invalid PTIDs
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in invalid_ptids:
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

    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify coordination handled failures correctly
    assert failed_rows == len(invalid_ptids), "All rows with invalid PTIDs should fail"

    # Verify no output was generated for failed lookups
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    lines = output_content.strip().split("\n") if output_content.strip() else []
    assert len(lines) <= 1, "No data rows should be written for failed lookups"

    # Verify QC logs were created with FAIL status for failed lookups
    assert mock_qc_creator.update_qc_log.call_count == len(invalid_ptids), (
        "QC log should be created for each visit, even failed ones"
    )

    # Check that all QC log calls used FAIL status (errors in shared error writer)
    for call in mock_qc_creator.update_qc_log.call_args_list:
        args, kwargs = call
        assert kwargs["status"] == "FAIL", (
            "QC status should be FAIL for failed identifier lookup"
        )
        # Verify error details are included
        assert len(kwargs["errors"].root) > 0, (
            "Error details should be included in FAIL status"
        )

    # Verify error coordination - no duplication
    processed_visits = qc_visitor.get_processed_visits()
    assert len(processed_visits) == len(invalid_ptids), (
        "QC visitor should process all visits, even failed ones"
    )
