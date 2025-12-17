"""Property test for visitor independence.

**Feature: identifier-lookup-event-logging, Property 6: Visitor Independence**
**Validates: Requirements 3.4**
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
from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


@given(
    num_ptids=st.integers(min_value=2, max_value=5),
    failing_visitor=st.sampled_from(["identifier", "qc", "event"]),
)
@settings(max_examples=100)
def test_visitor_independence(num_ptids: int, failing_visitor: str):  # noqa: C901
    """Property test: Visitor failures don't affect other visitors.

    **Feature: identifier-lookup-event-logging, Property 6: Visitor Independence**
    **Validates: Requirements 3.4**

    For any failure in one visitor (identifier lookup, QC logging, or event logging),
    the other visitors should continue processing without being affected.
    """
    # Arrange - Create test data
    ptids = [f"P{str(i).zfill(3)}" for i in range(1, num_ptids + 1)]

    # For identifier visitor failure, use empty identifiers map
    identifiers: Dict[str, IdentifierObject] = {}
    if failing_visitor != "identifier":
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

    # For QC visitor failure, make update_qc_log raise an exception
    if failing_visitor == "qc":
        mock_qc_creator.update_qc_log = Mock(
            side_effect=RuntimeError("Simulated QC logging failure")
        )
    else:
        mock_qc_creator.update_qc_log = Mock(return_value=True)

    # Create mock event logger
    mock_event_logger = Mock(spec=VisitEventLogger)

    # For event visitor failure, make log_event raise an exception
    if failing_visitor == "event":
        mock_event_logger.log_event = Mock(
            side_effect=RuntimeError("Simulated event logging failure")
        )
    else:
        mock_event_logger.log_event = Mock()

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
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

    # Create aggregate visitor with visit_all_strategy for independence
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

    # Process all rows
    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify visitor independence based on which visitor failed
    assert header_result, "Header processing should succeed"

    if failing_visitor == "identifier":
        # All rows should fail because identifier lookup fails
        assert failed_rows == len(ptids), (
            f"All rows should fail when identifier lookup fails. "
            f"Expected {len(ptids)} failed rows, got {failed_rows}"
        )

        # QC logging should still be called despite identifier lookup failure
        assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
            "QC logging should still be called despite identifier lookup failure"
        )

        # Event logging won't be called because rows are missing required fields
        # (no NACCID when identifier lookup fails). This is correct behavior -
        # event logging should only happen for valid visits.
        assert mock_event_logger.log_event.call_count == 0, (
            "Event logging should not be called for rows missing required fields"
        )

        # No output should be generated for failed identifier lookups
        output_stream.seek(0)
        output_content = output_stream.getvalue()
        lines = output_content.strip().split("\n") if output_content.strip() else []
        assert len(lines) <= 1, (
            "No data rows should be written for failed identifier lookups"
        )

    elif failing_visitor == "qc":
        # All rows should fail because QC logging fails
        assert failed_rows == len(ptids), (
            f"All rows should fail when QC logging fails. "
            f"Expected {len(ptids)} failed rows, got {failed_rows}"
        )

        # But identifier lookup and event logging should still work
        output_stream.seek(0)
        output_reader = csv.DictReader(output_stream)
        output_rows = list(output_reader)
        assert len(output_rows) == len(ptids), (
            "Identifier lookup should still produce output despite QC logging failure"
        )

        assert mock_event_logger.log_event.call_count == len(ptids), (
            "Event logging should still be called despite QC logging failure"
        )

        # Verify output has correct NACCIDs
        for i, output_row in enumerate(output_rows):
            expected_ptid = ptids[i]
            expected_naccid = identifiers[expected_ptid].naccid
            assert output_row["naccid"] == expected_naccid, (
                "Identifier lookup should work correctly despite QC logging failure"
            )

    elif failing_visitor == "event":
        # All rows should fail because event logging fails
        assert failed_rows == len(ptids), (
            f"All rows should fail when event logging fails. "
            f"Expected {len(ptids)} failed rows, got {failed_rows}"
        )

        # But identifier lookup and QC logging should still work
        output_stream.seek(0)
        output_reader = csv.DictReader(output_stream)
        output_rows = list(output_reader)
        assert len(output_rows) == len(ptids), (
            "Identifier lookup should still produce output despite event "
            "logging failure"
        )

        assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
            "QC logging should still be called despite event logging failure"
        )

        # Verify output has correct NACCIDs
        for i, output_row in enumerate(output_rows):
            expected_ptid = ptids[i]
            expected_naccid = identifiers[expected_ptid].naccid
            assert output_row["naccid"] == expected_naccid, (
                "Identifier lookup should work correctly despite event logging failure"
            )


def test_visitor_independence_partial_failures():
    """Property test: Partial visitor failures don't affect other visitors.

    **Feature: identifier-lookup-event-logging, Property 6: Visitor Independence**
    **Validates: Requirements 3.4**

    For any scenario where some rows succeed and some fail in one visitor,
    the other visitors should process all rows independently.
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
        identifiers=identifiers,
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

    # Create aggregate visitor with visit_all_strategy for independence
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

    # Process all rows
    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not aggregate_visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify visitor independence with partial failures
    assert header_result, "Header processing should succeed"

    # Some rows should fail (those without identifiers)
    expected_failures = num_ptids - len(identifiers)
    assert failed_rows == expected_failures, (
        f"Rows without identifiers should fail. "
        f"Expected {expected_failures} failed rows, got {failed_rows}"
    )

    # QC logging should still be called for ALL rows
    assert mock_qc_creator.update_qc_log.call_count == len(ptids), (
        f"QC logging should be called for all rows despite partial "
        f"identifier failures. Expected {len(ptids)} calls, "
        f"got {mock_qc_creator.update_qc_log.call_count}"
    )

    # Event logging should only be called for rows with valid identifiers
    # (rows without identifiers are missing required fields for event logging)
    assert mock_event_logger.log_event.call_count == len(identifiers), (
        f"Event logging should be called only for rows with valid "
        f"identifiers. Expected {len(identifiers)} calls, "
        f"got {mock_event_logger.log_event.call_count}"
    )

    # Identifier lookup should produce output only for successful rows
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(identifiers), (
        f"Identifier lookup should produce output only for successful rows. "
        f"Expected {len(identifiers)} output rows, got {len(output_rows)}"
    )

    # Verify output has correct NACCIDs for successful rows
    for output_row in output_rows:
        ptid = output_row["ptid"]
        expected_naccid = identifiers[ptid].naccid
        assert output_row["naccid"] == expected_naccid, (
            f"Output row for {ptid} should have correct NACCID"
        )
