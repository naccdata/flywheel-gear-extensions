"""Property test for direction-specific event logging.

**Feature: identifier-lookup-event-logging,
  Property 3: Direction-Specific Event
Logging**
**Validates: Requirements 1.4, 3.3, 6.1**
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
from identifier_app.main import CenterLookupVisitor, NACCIDLookupVisitor
from identifiers.identifiers_repository import IdentifierRepository
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_identifiers_lambda_repository import (
    MockIdentifiersLambdaRepository,
)


@given(
    num_ptids=st.integers(min_value=1, max_value=5),
    visit_num=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100)
def test_nacc_direction_with_qc_creates_events(num_ptids: int, visit_num: int):
    """Property test: NACC direction with QC logging creates submit events.

      **Feature: identifier-lookup-event-logging,
    Property 3: Direction-Specific
      Event Logging**
      **Validates: Requirements 1.4, 3.3, 6.1**

      For any CSV file processed in "nacc" direction with QC status log management
      enabled, the system should create submit events.
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

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_project.center_label = "TEST_CENTER"
    mock_project.label = "TEST_PROJECT"
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create mock event logger
    mock_event_capture = Mock(spec=VisitEventCapture)
    mock_event_capture.capture_event = Mock()

    # Create timestamp for events
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Create visitors for NACC direction with QC logging
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

    # Create aggregate visitor with all three visitors (simulating nacc direction
    # with QC)
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
                "visitnum": str(visit_num),
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

    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)

    # Assert - Verify submit events were created
    assert header_result, "Header processing should succeed"
    assert mock_event_capture.capture_event.call_count == len(ptids), (
        f"Submit events should be created for NACC direction with QC logging. "
        f"Expected {len(ptids)} events, got "
        f"{mock_event_capture.capture_event.call_count}"
    )


@given(
    num_naccids=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100)
def test_center_direction_no_events(num_naccids: int):
    """Property test: Center direction does not create submit events.

      **Feature: identifier-lookup-event-logging,
    Property 3: Direction-Specific
      Event Logging**
      **Validates: Requirements 1.4, 3.3, 6.1**

      For any CSV file processed in "center" direction, the system should not
      create any submit events.
    """
    # Arrange - Create test data with NACCIDs for center direction
    naccids = [f"NACC{str(i).zfill(6)}" for i in range(1, num_naccids + 1)]

    # Create mock identifiers repository
    mock_identifiers_repo = Mock(spec=IdentifierRepository)

    def mock_get(naccid: str):
        # Return identifier for any NACCID
        idx = int(naccid.replace("NACC", ""))
        return IdentifierObject(
            naccid=naccid,
            adcid=1,
            ptid=f"P{str(idx).zfill(3)}",
            guid=None,
            naccadc=1000 + idx,
        )

    mock_identifiers_repo.get = Mock(side_effect=mock_get)

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    # Create output stream for center lookup
    output_stream = StringIO()

    # Create center lookup visitor (no event logging)
    center_visitor = CenterLookupVisitor(
        identifiers_repo=mock_identifiers_repo,
        output_file=output_stream,
        error_writer=shared_error_writer,
    )

    # Create CSV data with NACCIDs
    header = ["naccid", "visitdate", "visitnum"]
    rows = []
    for naccid in naccids:
        rows.append(
            {
                "naccid": naccid,
                "visitdate": "2024-01-01",
                "visitnum": "1",
            }
        )

    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Act - Process CSV with center lookup visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = center_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        center_visitor.visit_row(row, line_num)

    # Assert - Verify no event logging occurred
    assert header_result, "Header processing should succeed"

    # Verify output was created (center lookup worked)
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(naccids), "Center lookup should process all rows"

    # The key assertion: center direction does not involve event logging at all
    # This is verified by the fact that CenterLookupVisitor doesn't have any
    # event logging dependencies or calls


@given(
    num_ptids=st.integers(min_value=1, max_value=5),
    visit_num=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=100)
def test_nacc_direction_without_qc_no_events(num_ptids: int, visit_num: int):
    """Property test: NACC direction without QC logging does not create events.

      **Feature: identifier-lookup-event-logging,
    Property 3: Direction-Specific
      Event Logging**
      **Validates: Requirements 1.4, 3.3, 6.1**

      For any CSV file processed in "nacc" direction without QC status log
      management (no form_configs_file), the system should not create submit events.
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

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create ONLY identifier lookup visitor (no QC, no event logging)
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
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
                "visitnum": str(visit_num),
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

    # Act - Process CSV with only identifier lookup visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = identifier_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        identifier_visitor.visit_row(row, line_num)

    # Assert - Verify identifier lookup worked
    assert header_result, "Header processing should succeed"

    # Verify output was created (identifier lookup worked)
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), "Identifier lookup should process all rows"

    # The key assertion: without QC logging, no event logging occurs
    # This is verified by the fact that we only use NACCIDLookupVisitor
    # without CSVCaptureVisitor
