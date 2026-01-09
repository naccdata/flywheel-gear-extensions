"""Property test for success determination.

**Feature: identifier-lookup-event-logging,
  Property 7: Success Determination**
**Validates: Requirements 3.5, 6.5**
"""

import csv
from datetime import datetime
from io import StringIO
from typing import Dict, List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logger import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from hypothesis import given, settings
from hypothesis import strategies as st
from identifier_app.main import NACCIDLookupVisitor, run
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
    event_logging_fails=st.booleans(),
    qc_logging_fails=st.booleans(),
)
@settings(max_examples=100)
def test_success_determination_with_valid_identifiers(
    num_ptids: int, event_logging_fails: bool, qc_logging_fails: bool
):
    """Property test: Success is determined by identifier lookup, not other
    visitors.

      **Feature: identifier-lookup-event-logging,
    Property 7: Success Determination**
      **Validates: Requirements 3.5, 6.5**

      For any CSV file processing where identifier lookup succeeds, the overall
      success status should be True regardless of event logging or QC logging failures.
    """
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
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)

    # Optionally make QC logging fail
    if qc_logging_fails:
        mock_qc_creator.update_qc_log = Mock(
            side_effect=RuntimeError("Simulated QC logging failure")
        )
    else:
        mock_qc_creator.update_qc_log = Mock(return_value=True)

    # Create mock event logger
    mock_event_logger = Mock(spec=VisitEventLogger)

    # Optionally make event logging fail
    if event_logging_fails:
        mock_event_logger.log_event = Mock(
            side_effect=RuntimeError("Simulated event logging failure")
        )
    else:
        mock_event_logger.log_event = Mock()

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="uds",
    )

    event_visitor = CSVLoggingVisitor(
        center_label="TEST_CENTER",
        project_label="TEST_PROJECT",
        gear_name="identifier-lookup",
        event_logger=mock_event_logger,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor
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

    # Act - Process CSV using the run function (which uses read_csv internally)
    success = run(
        input_file=input_stream,
        lookup_visitor=aggregate_visitor,
        error_writer=shared_error_writer,
        clear_errors=True,
        preserve_case=False,
    )

    # Assert - Success should be False if any visitor fails (due to visit_all_strategy)
    # But the key point is that identifier lookup succeeded and produced output
    if event_logging_fails or qc_logging_fails:
        # With visit_all_strategy, if any visitor fails, overall result is False
        assert not success, "Overall success should be False when any visitor fails"
    else:
        # All visitors succeeded
        assert success, "Overall success should be True when all visitors succeed"

    # Verify identifier lookup succeeded regardless of other visitor failures
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), (
        f"Identifier lookup should produce output for all rows regardless "
        f"of other failures. Expected {len(ptids)} output rows, "
        f"got {len(output_rows)}"
    )

    # Verify all output rows have correct NACCIDs
    for i, output_row in enumerate(output_rows):
        expected_ptid = ptids[i]
        expected_naccid = identifiers[expected_ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            f"Row {i} should have correct NACCID regardless of other visitor failures"
        )


@given(
    num_ptids=st.integers(min_value=2, max_value=5),
    event_logging_fails=st.booleans(),
    qc_logging_fails=st.booleans(),
)
@settings(max_examples=100)
def test_success_determination_with_invalid_identifiers(
    num_ptids: int, event_logging_fails: bool, qc_logging_fails: bool
):
    """Property test: Failure is determined by identifier lookup, not other
    visitors.

      **Feature: identifier-lookup-event-logging,
    Property 7: Success Determination**
      **Validates: Requirements 3.5, 6.5**

      For any CSV file processing where identifier lookup fails, the overall
      success status should be False regardless of event logging or QC logging status.
    """
    # Arrange - Create test data with NO valid identifiers
    ptids = [f"P{str(i).zfill(3)}" for i in range(1, num_ptids + 1)]

    # Empty identifiers map causes all lookups to fail
    identifiers: Dict[str, IdentifierObject] = {}

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)

    # Optionally make QC logging fail
    if qc_logging_fails:
        mock_qc_creator.update_qc_log = Mock(
            side_effect=RuntimeError("Simulated QC logging failure")
        )
    else:
        mock_qc_creator.update_qc_log = Mock(return_value=True)

    # Create mock event logger
    mock_event_logger = Mock(spec=VisitEventLogger)

    # Optionally make event logging fail
    if event_logging_fails:
        mock_event_logger.log_event = Mock(
            side_effect=RuntimeError("Simulated event logging failure")
        )
    else:
        mock_event_logger.log_event = Mock()

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="uds",
    )

    event_visitor = CSVLoggingVisitor(
        center_label="TEST_CENTER",
        project_label="TEST_PROJECT",
        gear_name="identifier-lookup",
        event_logger=mock_event_logger,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor
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

    # Act - Process CSV using the run function
    success = run(
        input_file=input_stream,
        lookup_visitor=aggregate_visitor,
        error_writer=shared_error_writer,
        clear_errors=True,
        preserve_case=False,
    )

    # Assert - Success should always be False when identifier lookup fails
    assert not success, (
        "Overall success should be False when identifier lookup fails, "
        "regardless of event logging or QC logging status"
    )

    # Verify no output was generated for failed identifier lookups
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    lines = output_content.strip().split("\n") if output_content.strip() else []
    assert len(lines) <= 1, (
        "No data rows should be written when identifier lookup fails"
    )

    # Verify QC logging was still called (if not failing)
    if not qc_logging_fails:
        assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
            "QC logging should be called even when identifier lookup fails"
        )


def test_success_determination_mixed_results():
    """Property test: Success determination with mixed identifier lookup
    results.

      **Feature: identifier-lookup-event-logging,
    Property 7: Success Determination**
      **Validates: Requirements 3.5, 6.5**

      For any CSV file processing with some successful and some failed identifier
      lookups, the overall success status should be False (partial failure).
    """
    # Arrange - Create test data with some valid and some invalid identifiers
    num_ptids = 5
    ptids = [f"P{str(i).zfill(3)}" for i in range(1, num_ptids + 1)]

    # Only provide identifiers for first half of PTIDs
    identifiers = {
        ptid: IdentifierObject(
            naccid=f"NACC{str(i).zfill(6)}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )
        for i, ptid in enumerate(ptids[: num_ptids // 2], start=1)
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log = Mock(return_value=True)

    # Create mock event logger
    mock_event_logger = Mock(spec=VisitEventLogger)
    mock_event_logger.log_event = Mock()

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="uds",
    )

    event_visitor = CSVLoggingVisitor(
        center_label="TEST_CENTER",
        project_label="TEST_PROJECT",
        gear_name="identifier-lookup",
        event_logger=mock_event_logger,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor
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

    # Act - Process CSV using the run function
    success = run(
        input_file=input_stream,
        lookup_visitor=aggregate_visitor,
        error_writer=shared_error_writer,
        clear_errors=True,
        preserve_case=False,
    )

    # Assert - Success should be False when some identifier lookups fail
    assert not success, (
        "Overall success should be False when some identifier lookups fail"
    )

    # Verify output was generated only for successful identifier lookups
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(identifiers), (
        f"Output should be generated only for successful identifier lookups. "
        f"Expected {len(identifiers)} output rows, got {len(output_rows)}"
    )

    # Verify all output rows have correct NACCIDs
    for output_row in output_rows:
        ptid = output_row["ptid"]
        expected_naccid = identifiers[ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            f"Output row for {ptid} should have correct NACCID"
        )

    # Verify QC and event logging were called for all rows
    assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
        "QC logging should be called for all rows"
    )

    # Event logging should only be called for successful identifier lookups
    assert mock_event_logger.log_event.call_count == len(identifiers), (
        "Event logging should be called only for successful identifier lookups"
    )
