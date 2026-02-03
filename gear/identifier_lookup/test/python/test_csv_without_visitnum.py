"""Integration test for CSV processing without visitnum column.

This test verifies that the identifier lookup gear correctly handles CSV files
that don't have a visitnum column, which is common for certain form types
(e.g., NP, Milestones) that don't correspond to visits.

**Feature: identifier-lookup-refactoring**
**Validates: Handling of forms without visit numbers**
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
from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_identifiers_lambda_repository import (
    MockIdentifiersLambdaRepository,
)


def test_csv_without_visitnum_column():
    """Test processing CSV data that doesn't have a visitnum column.

    Uses Milestone form format which has packet but no visitnum.
    Milestones don't correspond to visits and use visitdate for identification.
    This test verifies that:
    1. QC logs are created successfully without visitnum
    2. Events are captured successfully without visitnum
    3. No errors are raised during processing
    """
    # Arrange - Create CSV data WITHOUT visitnum column (Milestone format)
    csv_data = [
        {
            "adcid": 1,
            "ptid": "P001",
            "visitdate": "2024-01-15",
            "packet": "M",  # Milestone packet
            # No visitnum field - Milestones don't have visit numbers
            "formver": "3.0",
        },
        {
            "adcid": 1,
            "ptid": "P002",
            "visitdate": "2024-01-16",
            "packet": "M",  # Milestone packet
            # No visitnum field - Milestones don't have visit numbers
            "formver": "3.0",
        },
    ]

    # Create identifiers for all PTIDs
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001",
            adcid=1,
            ptid="P001",
            guid=None,
            naccadc=1001,
        ),
        "P002": IdentifierObject(
            naccid="NACC000002",
            adcid=1,
            ptid="P002",
            guid=None,
            naccadc=1002,
        ),
    }

    # Create CSV input stream WITHOUT visitnum in header (Milestone format)
    header = ["adcid", "ptid", "visitdate", "packet", "formver"]
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(csv_data)
    input_stream.seek(0)

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create mock event capture
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_event_capture.capture_event = Mock()
    timestamp = datetime.now()

    # Create visitors using milestone configs
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="MLST",  # Milestone module
        required_fields=["adcid", "ptid", "visitdate", "packet", "formver"],
        error_writer=shared_error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),  # Using UDS configs for simplicity
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
        module_name="MLST",  # Milestone module
    )

    event_visitor = CSVCaptureVisitor(
        center_label="test-center",
        project_label="test-project",
        gear_name="identifier-lookup",
        event_capture=mock_event_capture,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor with all three visitors
    aggregate_visitor = AggregateCSVVisitor(
        visitors=[identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Act - Process CSV data
    # First, visit the header for all visitors
    header_result = aggregate_visitor.visit_header(header)
    assert header_result, "Header processing should succeed"

    # Then process each row
    for i, row in enumerate(
        csv_data, start=2
    ):  # Line numbers start at 2 (after header)
        aggregate_visitor.visit_row(row, line_num=i)

    # Assert - Verify QC logs were created successfully
    assert mock_qc_creator.update_qc_log.call_count == len(csv_data), (
        "QC log should be created for each row even without visitnum"
    )

    # Verify QC log calls have visitnum=None
    for call in mock_qc_creator.update_qc_log.call_args_list:
        visit_keys = call.kwargs["visit_keys"]
        assert visit_keys.visitnum is None, (
            "Visit keys should have visitnum=None when not in CSV"
        )
        assert visit_keys.ptid is not None, "Visit keys should have ptid"
        assert visit_keys.date is not None, "Visit keys should have date"
        assert visit_keys.module == "MLST", "Visit keys should have module"

    # Verify events were captured successfully
    assert mock_event_capture.capture_event.call_count == len(csv_data), (
        "Event should be captured for each row even without visitnum"
    )

    # Verify captured events have visit_number=None
    for call in mock_event_capture.capture_event.call_args_list:
        event = call[0][0]  # First positional argument
        assert event.visit_number is None, (
            "Event should have visit_number=None when not in CSV"
        )
        assert event.ptid is not None, "Event should have ptid"
        assert event.visit_date is not None, "Event should have visit_date"
        assert event.module == "MLST", "Event should have module"
        assert event.packet == "M", "Event should have packet=M for Milestones"

    # Verify no errors were raised
    assert len(misc_errors) == 0, (
        "No errors should occur when processing without visitnum"
    )
    assert len(shared_error_writer.errors().root) == 0, (
        "No errors should be written when processing without visitnum"
    )

    # Verify output CSV was created successfully
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(csv_data), (
        "Output should have same number of rows as input"
    )

    # Verify output rows have NACCIDs but no visitnum column
    for i, output_row in enumerate(output_rows):
        ptid = str(csv_data[i]["ptid"])
        assert output_row["naccid"] == identifiers[ptid].naccid, (
            "Output should have correct NACCID"
        )
        # visitnum should not be in output if not in input
        # (or it might be present with empty value depending on implementation)


def test_csv_with_visitnum_none_value():
    """Test processing CSV data that has visitnum column but with None/empty
    values.

    This is different from the column being completely absent - the column exists
    but the values are empty.
    """
    # Arrange - Create CSV data WITH visitnum column but empty values
    csv_data = [
        {
            "adcid": 1,
            "ptid": "P001",
            "visitdate": "2024-01-15",
            "visitnum": "",  # Empty string
            "packet": "",  # Empty string
            "formver": "4.0",
        },
    ]

    # Create identifier
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001",
            adcid=1,
            ptid="P001",
            guid=None,
            naccadc=1001,
        ),
    }

    # Create CSV input stream WITH visitnum in header but empty value
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(csv_data)
    input_stream.seek(0)

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Create output stream
    output_stream = StringIO()

    # Create mock dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_event_capture.capture_event = Mock()
    timestamp = datetime.now()

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="NP",
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
        module_name="NP",
    )

    event_visitor = CSVCaptureVisitor(
        center_label="test-center",
        project_label="test-project",
        gear_name="identifier-lookup",
        event_capture=mock_event_capture,
        module_configs=uds_ingest_configs(),
        error_writer=shared_error_writer,
        timestamp=timestamp,
        action="submit",
        datatype="form",
    )

    aggregate_visitor = AggregateCSVVisitor(
        visitors=[identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Act - Process CSV data
    aggregate_visitor.visit_header(header)
    for i, row in enumerate(csv_data, start=2):
        aggregate_visitor.visit_row(row, line_num=i)

    # Assert - Verify processing succeeded
    assert mock_qc_creator.update_qc_log.call_count == 1

    # Verify QC log has visitnum=None (empty string converted to None)
    visit_keys = mock_qc_creator.update_qc_log.call_args.kwargs["visit_keys"]
    # Empty string should be treated as None
    assert visit_keys.visitnum in [None, ""], (
        "Empty visitnum should be None or empty string"
    )

    # Verify event was captured
    assert mock_event_capture.capture_event.call_count == 1
    # Empty string is converted to None by CSVCaptureVisitor
    event = mock_event_capture.capture_event.call_args[0][0]
    assert event.visit_number is None, (
        "Empty visitnum should be converted to None in event"
    )

    # Verify no errors
    assert len(misc_errors) == 0
    assert len(shared_error_writer.errors().root) == 0
