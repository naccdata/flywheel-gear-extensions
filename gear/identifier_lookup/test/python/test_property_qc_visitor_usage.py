"""Property test for QC visitor usage.

**Feature: identifier-lookup-refactoring, Property 10: QC Visitor Usage**
**Validates: Requirements 2.1**
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


@st.composite
def csv_data_strategy(draw):
    """Generate random CSV data with multiple visits.

    Note: PTIDs are generated with format "P###" to avoid issues with
    clean_ptid() which strips leading zeros. This ensures PTIDs remain valid
    after cleaning.
    """
    num_visits = draw(st.integers(min_value=1, max_value=5))
    visits = []

    for _i in range(num_visits):
        ptid = f"P{draw(st.integers(min_value=1, max_value=999)):03d}"
        date = draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d")))
        visitnum = draw(st.integers(min_value=1, max_value=99).map(str))

        visits.append(
            {
                "adcid": 1,
                "ptid": ptid,
                "visitdate": date,
                "visitnum": visitnum,
                "packet": "I",
                "formver": "4.0",
            }
        )

    return visits


@given(csv_data=csv_data_strategy())
@settings(max_examples=100)
def test_qc_visitor_creates_visit_specific_logs(csv_data: List[Dict[str, str]]):
    """Property test: QCStatusLogCSVVisitor creates visit-specific QC status
    logs.

    **Feature: identifier-lookup-refactoring, Property 10: QC Visitor Usage**
    **Validates: Requirements 2.1**

    For any CSV processing requiring QC logging, the system should use
    QCStatusLogCSVVisitor to create visit-specific QC status logs.
    """
    # Arrange - Create identifiers for all PTIDs in the CSV data
    identifiers = {}
    for i, visit in enumerate(csv_data):
        ptid = visit["ptid"]
        identifiers[ptid] = IdentifierObject(
            naccid=f"NACC{i:06d}",
            adcid=1,
            ptid=ptid,
            guid=None,
            naccadc=1000 + i,
        )

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Use QCStatusLogCSVVisitor for QC logging
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

    # Create CSV input stream
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(csv_data)
    input_stream.seek(0)

    # Act - Process CSV with aggregate visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    aggregate_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)

    # Assert - Verify QCStatusLogCSVVisitor was used to create visit-specific logs
    assert mock_qc_creator.update_qc_log.call_count == len(csv_data), (
        "QCStatusLogCSVVisitor should create one QC log per visit"
    )

    # Verify each QC log call has visit-specific information
    for _i, call in enumerate(mock_qc_creator.update_qc_log.call_args_list):
        _args, kwargs = call
        visit_keys = kwargs["visit_keys"]

        # Verify visit keys contain visit-specific information
        assert visit_keys.ptid is not None, "Visit keys should have PTID"
        assert visit_keys.date is not None, "Visit keys should have date"
        assert visit_keys.module == "TEST", "Visit keys should have module"

        # Verify the visit keys match one of the input visits
        matching_visit = next(
            (
                v
                for v in csv_data
                if v["ptid"] == visit_keys.ptid and v["visitdate"] == visit_keys.date
            ),
            None,
        )
        assert matching_visit is not None, (
            f"Visit keys should match input data: {visit_keys.ptid}, {visit_keys.date}"
        )

    # Verify processed visits are tracked
    processed_visits = qc_visitor.get_processed_visits()
    assert len(processed_visits) == len(csv_data), (
        "QC visitor should track all processed visits"
    )


def test_qc_visitor_usage_with_identifier_lookup():
    """Test QC visitor usage in conjunction with identifier lookup.

    **Feature: identifier-lookup-refactoring, Property 10: QC Visitor Usage**
    **Validates: Requirements 2.1**

    When processing CSV data for QC logging, the system should use
    QCStatusLogCSVVisitor to create visit-specific QC status logs that
    reflect the results of identifier lookup.
    """
    # Arrange - Create test data with some valid and some invalid identifiers
    csv_data = [
        {
            "adcid": 1,
            "ptid": "P001",
            "visitdate": "2024-01-01",
            "visitnum": "1",
            "packet": "I",
            "formver": "4.0",
        },
        {
            "adcid": 1,
            "ptid": "INVALID",
            "visitdate": "2024-01-02",
            "visitnum": "2",
            "packet": "I",
            "formver": "4.0",
        },
        {
            "adcid": 1,
            "ptid": "P003",
            "visitdate": "2024-01-03",
            "visitnum": "3",
            "packet": "I",
            "formver": "4.0",
        },
    ]

    # Create identifiers only for valid PTIDs
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        ),
        "P003": IdentifierObject(
            naccid="NACC000003", adcid=1, ptid="P003", guid=None, naccadc=1003
        ),
    }

    # Create shared error writer
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create output stream for identifier lookup
    output_stream = StringIO()

    # Create mock QC dependencies
    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    # Create visitors
    identifier_visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=shared_error_writer,
        misc_errors=misc_errors,
    )

    # Use QCStatusLogCSVVisitor for QC logging
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

    # Create CSV input stream
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver"]
    input_stream = StringIO()
    writer = csv.DictWriter(input_stream, fieldnames=header)
    writer.writeheader()
    writer.writerows(csv_data)
    input_stream.seek(0)

    # Act - Process CSV with aggregate visitor
    csv_reader = csv.DictReader(input_stream)
    header_list = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    aggregate_visitor.visit_header(header_list)

    for line_num, row in enumerate(csv_reader, start=2):
        aggregate_visitor.visit_row(row, line_num)

    # Assert - Verify QCStatusLogCSVVisitor created logs for all visits
    assert mock_qc_creator.update_qc_log.call_count == len(csv_data), (
        "QC log should be created for each visit, "
        "regardless of identifier lookup result"
    )

    # Verify QC status reflects identifier lookup results
    qc_calls = mock_qc_creator.update_qc_log.call_args_list

    # First visit (P001) should have PASS status
    assert qc_calls[0][1]["status"] == "PASS", (
        "First visit should have PASS status (valid identifier)"
    )

    # Second visit (INVALID) should have FAIL status
    assert qc_calls[1][1]["status"] == "FAIL", (
        "Second visit should have FAIL status (invalid identifier)"
    )

    # Third visit (P003) should have PASS status
    assert qc_calls[2][1]["status"] == "PASS", (
        "Third visit should have PASS status (valid identifier)"
    )
