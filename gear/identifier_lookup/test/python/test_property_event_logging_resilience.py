"""Property test for event logging resilience.

**Feature: identifier-lookup-event-logging,
  Property 4: Event Logging Resilience**
**Validates: Requirements 1.5**
"""

import csv
from datetime import datetime
from io import StringIO
from typing import List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from event_capture.csv_capture_visitor import CSVCaptureVisitor
from event_capture.event_capture import VisitEventCapture
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from hypothesis import given, settings
from hypothesis import strategies as st
from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_identifiers_lambda_repository import (
    MockIdentifiersLambdaRepository,
)


@given(
    num_ptids=st.integers(min_value=2, max_value=5),
    failure_row=st.integers(min_value=0, max_value=4),
)
@settings(max_examples=100)
def test_event_logging_resilience(num_ptids: int, failure_row: int):
    """Property test: Event logging failures don't prevent subsequent
    processing.

      **Feature: identifier-lookup-event-logging,
    Property 4: Event Logging Resilience**
      **Validates: Requirements 1.5**

      For any event logging failure during visit processing, the system should
      continue processing subsequent visits without failing the entire operation.
    """
    # Ensure failure_row is within bounds
    if failure_row >= num_ptids:
        failure_row = num_ptids - 1

    # Arrange - Create test data with valid identifiers
    ptids = [f"P{str(i).zfill(3)}" for i in range(1, num_ptids + 1)]

    identifiers = {
        ptid: IdentifierObject(
            naccid=f"NACC{str(i).zfill(6)}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )
        for i, ptid in enumerate(ptids, start=1)
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create mock event logger that fails on a specific row
    mock_event_capture = Mock(spec=VisitEventCapture)

    # Track call count to determine when to fail
    call_count = [0]

    def capture_event_with_failure(event):
        """Mock capture_event that fails on a specific row."""
        if call_count[0] == failure_row:
            call_count[0] += 1
            raise RuntimeError(f"Simulated event logging failure for row {failure_row}")
        call_count[0] += 1

    mock_event_capture.capture_event = Mock(side_effect=capture_event_with_failure)

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
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
        module_name="uds",
    )

    event_visitor = CSVCaptureVisitor(
        center_label="TEST_CENTER",
        project_label="TEST_PROJECT",
        gear_name="identifier-lookup",
        event_capture=mock_event_capture,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor with visit_all_strategy for resilience
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Create CSV data with valid visit rows
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in ptids:
        rows.append(
            {
                "adcid": "1",
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

    # Process all rows - event logging will fail on one row but processing continues
    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify resilience
    assert header_result, "Header processing should succeed"

    # All rows should fail because event logging failure causes the aggregate to fail
    # But the key is that ALL rows are still processed (not short-circuited)
    assert failed_rows == 1, (
        f"Only the row with event logging failure should fail. "
        f"Expected 1 failed row, got {failed_rows}"
    )

    # Verify identifier lookup still processed ALL rows despite event logging failure
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), (
        f"Identifier lookup should process all rows despite event logging failure. "
        f"Expected {len(ptids)} output rows, got {len(output_rows)}"
    )

    # Verify QC logging still processed ALL rows despite event logging failure
    assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
        f"QC logging should process all rows despite event logging failure. "
        f"Expected {len(ptids)} QC log calls, "
        f"got {mock_qc_creator.update_qc_log.call_count}"
    )

    # Verify event logger was called for all rows (including the one that failed)
    assert mock_event_capture.capture_event.call_count == len(ptids), (
        f"Event logger should be called for all rows. "
        f"Expected {len(ptids)} calls, got "
        f"{mock_event_capture.capture_event.call_count}"
    )

    # Verify all output rows have correct NACCIDs
    for i, output_row in enumerate(output_rows):
        expected_ptid = ptids[i]
        expected_naccid = identifiers[expected_ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            f"Row {i} should have correct NACCID despite event logging failure"
        )


def test_event_logging_resilience_multiple_failures():
    """Property test: Multiple event logging failures don't prevent processing.

      **Feature: identifier-lookup-event-logging,
    Property 4: Event Logging Resilience**
      **Validates: Requirements 1.5**

      For any scenario with multiple event logging failures, the system should
      continue processing all visits without failing the entire operation.
    """
    # Arrange - Create test data with valid identifiers
    num_ptids = 5
    ptids = [f"P{str(i).zfill(3)}" for i in range(1, num_ptids + 1)]

    identifiers = {
        ptid: IdentifierObject(
            naccid=f"NACC{str(i).zfill(6)}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )
        for i, ptid in enumerate(ptids, start=1)
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create mock event logger that always fails
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_event_capture.capture_event = Mock(
        side_effect=RuntimeError("Simulated event logging failure")
    )

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
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
        module_name="uds",
    )

    event_visitor = CSVCaptureVisitor(
        center_label="TEST_CENTER",
        project_label="TEST_PROJECT",
        gear_name="identifier-lookup",
        event_capture=mock_event_capture,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor with visit_all_strategy for resilience
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Create CSV data with valid visit rows
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    rows = []
    for ptid in ptids:
        rows.append(
            {
                "adcid": "1",
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

    # Process all rows - event logging will fail on all rows but processing continues
    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify resilience with multiple failures
    assert header_result, "Header processing should succeed"

    # All rows should fail because event logging fails on all rows
    assert failed_rows == len(ptids), (
        f"All rows should fail due to event logging failures. "
        f"Expected {len(ptids)} failed rows, got {failed_rows}"
    )

    # Verify identifier lookup still processed ALL rows despite all event
    # logging failures
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), (
        f"Identifier lookup should process all rows despite all event "
        f"logging failures. Expected {len(ptids)} output rows, "
        f"got {len(output_rows)}"
    )

    # Verify QC logging still processed ALL rows despite all event logging
    # failures
    assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
        f"QC logging should process all rows despite all event logging "
        f"failures. Expected {len(ptids)} QC log calls, "
        f"got {mock_qc_creator.update_qc_log.call_count}"
    )

    # Verify event logger was called for all rows (all failed)
    assert mock_event_capture.capture_event.call_count == len(ptids), (
        "Event logger should be called for all rows. "
        f"Expected {len(ptids)} calls, got "
        f"{mock_event_capture.capture_event.call_count}"
    )

    # Verify all output rows have correct NACCIDs
    for i, output_row in enumerate(output_rows):
        expected_ptid = ptids[i]
        expected_naccid = identifiers[expected_ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            f"Row {i} should have correct NACCID despite event logging failures"
        )
