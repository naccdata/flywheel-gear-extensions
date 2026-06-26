"""Property test for output format preservation.

**Feature: identifier-lookup-event-logging,
  Property 8: Output Format Preservation**
**Validates: Requirements 6.4**
"""

import csv
from datetime import datetime
from io import StringIO
from typing import Dict, List
from unittest.mock import Mock

from error_logging.qc_status_log_creator import QCStatusLogManager
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from event_capture.csv_capture_visitor import CSVCaptureVisitor
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from hypothesis import given
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
    num_ptids=st.integers(min_value=1, max_value=5),
    include_optional_fields=st.booleans(),
)
def test_output_format_preservation_property(
    num_ptids: int, include_optional_fields: bool
):
    """Property test: Output format preservation with event logging.

      **Feature: identifier-lookup-event-logging,
    Property 8: Output Format Preservation**
      **Validates: Requirements 6.4**

      For any CSV file processed with valid identifiers, the output file format
      and QC metadata structure should remain identical whether event logging
      is enabled or not.
    """
    # Generate test data
    ptids = [f"P{i:03d}" for i in range(1, num_ptids + 1)]
    identifiers = {
        ptid: IdentifierObject(
            naccid=f"NACC{i:06d}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )
        for i, ptid in enumerate(ptids, 1)
    }

    # Create base CSV header and rows
    base_header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    if include_optional_fields:
        base_header.extend(["var1", "var2"])

    rows = []
    for i, ptid in enumerate(ptids):
        row = {
            "adcid": 1,
            "ptid": ptid,
            "visitdate": f"2024-01-{i + 1:02d}",
            "visitnum": str(i + 1),
            "packet": "I" if i % 2 == 0 else "F",
            "formver": "4.0",
        }
        if include_optional_fields:
            row["var1"] = f"value{i + 1}"
            row["var2"] = f"data{i + 1}"
        rows.append(row)

    # Test WITHOUT event logging (baseline)
    baseline_result = _process_csv_without_event_logging(identifiers, base_header, rows)

    # Test WITH event logging
    event_logging_result = _process_csv_with_event_logging(
        identifiers, base_header, rows
    )

    # Assert output format is identical
    assert baseline_result["fieldnames"] == event_logging_result["fieldnames"], (
        "CSV fieldnames should be identical with and without event logging"
    )

    assert len(baseline_result["rows"]) == len(event_logging_result["rows"]), (
        "Number of output rows should be identical"
    )

    # Compare each row's content
    for i, (baseline_row, event_row) in enumerate(
        zip(baseline_result["rows"], event_logging_result["rows"], strict=False)
    ):
        for field in baseline_result["fieldnames"] or []:
            assert baseline_row[field] == event_row[field], (
                f"Row {i} field '{field}' should be identical: "
                f"'{baseline_row[field]}' != '{event_row[field]}'"
            )

    # Assert QC metadata structure is identical
    assert len(baseline_result["qc_calls"]) == len(event_logging_result["qc_calls"]), (
        "Number of QC log calls should be identical"
    )

    # Compare QC call structure
    for i, (baseline_call, event_call) in enumerate(
        zip(baseline_result["qc_calls"], event_logging_result["qc_calls"], strict=False)
    ):
        baseline_args, baseline_kwargs = baseline_call
        event_args, event_kwargs = event_call

        # Compare status (most important QC metadata)
        assert baseline_kwargs["status"] == event_kwargs["status"], (
            f"QC call {i} status should be identical"
        )

        # Compare visit information structure
        baseline_visit = baseline_kwargs.get("visit")
        event_visit = event_kwargs.get("visit")
        if baseline_visit and event_visit:
            assert baseline_visit.ptid == event_visit.ptid, (
                f"QC call {i} visit PTID should be identical"
            )
            assert baseline_visit.module == event_visit.module, (
                f"QC call {i} visit module should be identical"
            )


def _process_csv_without_event_logging(
    identifiers: Dict[str, IdentifierObject], header: List[str], rows: List[Dict]
) -> Dict:
    """Process CSV without event logging and return results."""
    # Create error writer and output stream
    error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create visitors WITHOUT event logging
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",  # Use valid module name
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=error_writer,
        misc_errors=misc_errors,
        module_name="uds",  # Use valid module name
    )

    # Create aggregate visitor
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor], strategy_builder=visit_all_strategy
    )

    # Process CSV
    _process_csv_data(aggregate_visitor, header, rows)

    # Return results
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    if output_content.strip():
        reader = csv.DictReader(StringIO(output_content))
        fieldnames = reader.fieldnames
        output_rows = list(reader)
    else:
        fieldnames = None
        output_rows = []

    return {
        "fieldnames": fieldnames,
        "rows": output_rows,
        "qc_calls": mock_qc_creator.update_qc_log.call_args_list,
    }


def _process_csv_with_event_logging(
    identifiers: Dict[str, IdentifierObject], header: List[str], rows: List[Dict]
) -> Dict:
    """Process CSV with event logging and return results."""
    # Create error writer and output stream
    error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create mock event logging dependencies
    mock_event_capture = Mock()
    mock_event_capture.capture_event.return_value = None

    # Create visitors WITH event logging
    identifier_visitor = NACCIDLookupVisitor(
        identifiers_repo=MockIdentifiersLambdaRepository(identifiers),
        output_file=output_stream,
        module_name="uds",  # Use valid module name
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
    )

    misc_errors: List[FileError] = []
    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=error_writer,
        misc_errors=misc_errors,
        module_name="uds",  # Use valid module name
    )

    event_visitor = CSVCaptureVisitor(
        center_label="test-center",
        project_label="test-project",
        gear_name="identifier-lookup",
        event_capture=mock_event_capture,
        module_configs=uds_ingest_configs(),
        error_writer=error_writer,
        timestamp=datetime.now(),
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor with all three visitors
    aggregate_visitor = AggregateCSVVisitor(
        [identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Process CSV
    _process_csv_data(aggregate_visitor, header, rows)

    # Return results
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    if output_content.strip():
        reader = csv.DictReader(StringIO(output_content))
        fieldnames = reader.fieldnames
        output_rows = list(reader)
    else:
        fieldnames = None
        output_rows = []

    return {
        "fieldnames": fieldnames,
        "rows": output_rows,
        "qc_calls": mock_qc_creator.update_qc_log.call_args_list,
    }


def _process_csv_data(aggregate_visitor, header: List[str], rows: List[Dict]):
    """Helper function to process CSV data with a visitor."""
    # Create CSV input stream
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    input_stream.seek(0)

    # Process CSV
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    aggregate_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)
