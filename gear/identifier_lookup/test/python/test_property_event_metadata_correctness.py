"""Property test for event metadata correctness.

**Feature: identifier-lookup-event-logging,
  Property 5: Event Metadata Correctness**
**Validates: Requirements 2.2, 2.4, 2.5, 2.6**
"""

from datetime import datetime
from io import StringIO
from unittest.mock import Mock

from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logger import VisitEventLogger
from event_logging.visit_events import VisitEvent
from hypothesis import given
from hypothesis import strategies as st
from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from inputs.csv_reader import AggregateCSVVisitor, visit_all_strategy
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


# Strategy for generating valid CSV rows with visit data
@st.composite
def valid_csv_row(draw):
    """Generate a valid CSV row with all required fields."""
    # Generate valid PTID matching pattern ^[!-~]{1,10}$ (printable ASCII)
    # Avoid sequences of all zeros as leading zeros are stripped
    # Use letters and numbers but ensure it's not all zeros
    ptid_base = draw(
        st.text(min_size=1, max_size=9, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
    )
    # Add a prefix to ensure it's never all zeros or empty
    ptid = f"P{ptid_base}" if ptid_base else "P001"
    # Truncate to max 10 characters
    ptid = ptid[:10]

    adcid = draw(st.integers(min_value=1, max_value=999))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD", "MDS"]))
    packet = draw(st.sampled_from(["I", "F", "T", "M", "R"]))
    visitnum = draw(st.integers(min_value=1, max_value=20))
    visitdate = draw(
        st.dates(
            min_value=datetime(2020, 1, 1).date(),
            max_value=datetime(2024, 12, 31).date(),
        )
    )
    formver = draw(st.sampled_from(["4.0", "3.0"]))

    return {
        "ptid": ptid,
        "adcid": str(adcid),
        "module": module,
        "packet": packet,
        "visitnum": str(visitnum),
        "visitdate": visitdate.strftime("%Y-%m-%d"),
        "formver": formver,
    }


# Strategy for generating event metadata
@st.composite
def event_metadata(draw):
    """Generate event metadata parameters."""
    # Use safe character sets to avoid empty strings
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    center_label = draw(st.text(min_size=1, max_size=50, alphabet=safe_chars))
    project_label = draw(st.text(min_size=1, max_size=50, alphabet=safe_chars))
    gear_name = draw(st.text(min_size=1, max_size=30, alphabet=safe_chars))
    timestamp = draw(
        st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))
    )

    # Ensure no empty strings
    if not center_label:
        center_label = "test-center"
    if not project_label:
        project_label = "test-project"
    if not gear_name:
        gear_name = "test-gear"

    return {
        "center_label": center_label,
        "project_label": project_label,
        "gear_name": gear_name,
        "timestamp": timestamp,
    }


@given(csv_row=valid_csv_row(), metadata=event_metadata())
def test_property_event_metadata_correctness(csv_row, metadata):
    """Property: For any submit event created, the event should contain correct
      center label, project label, gear name, file creation timestamp,
      datatype='form', and packet value if present in the CSV row.

      **Feature: identifier-lookup-event-logging,
    Property 5: Event Metadata Correctness**
      **Validates: Requirements 2.2, 2.4, 2.5, 2.6**
    """
    # Arrange - Create identifiers for the PTID
    identifiers = {
        csv_row["ptid"]: IdentifierObject(
            ptid=csv_row["ptid"],
            naccid=f"NACC{hash(csv_row['ptid']) % 1000000:06d}",
            adcid=int(csv_row["adcid"]),
            guid=None,
            naccadc=int(csv_row["adcid"]) * 1000,
        )
    }

    # Mock dependencies
    mock_qc_creator = Mock()
    mock_qc_creator.update_qc_log.return_value = True

    mock_event_logger = Mock(spec=VisitEventLogger)

    # Create visitors
    error_writer = ListErrorWriter(container_id="test", fw_path="test/path")
    output_stream = StringIO()

    identifier_visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
        misc_errors=[],
        validator=None,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=Mock(),
        qc_log_creator=mock_qc_creator,
        gear_name=metadata["gear_name"],
        error_writer=error_writer,
        module_name="uds",
    )

    event_visitor = CSVLoggingVisitor(
        center_label=metadata["center_label"],
        project_label=metadata["project_label"],
        gear_name=metadata["gear_name"],
        event_logger=mock_event_logger,
        module_configs=uds_ingest_configs(),
        error_writer=error_writer,
        timestamp=metadata["timestamp"],
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor
    aggregate_visitor = AggregateCSVVisitor(
        visitors=[identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Act - Process the CSV row
    header = ["ptid", "adcid", "module", "packet", "visitnum", "visitdate", "formver"]
    aggregate_visitor.visit_header(header)
    aggregate_visitor.visit_row(csv_row, 1)

    # Assert - Verify event metadata correctness
    mock_event_logger.log_event.assert_called_once()
    event_call = mock_event_logger.log_event.call_args[0][0]
    assert isinstance(event_call, VisitEvent)

    # Verify all metadata fields are correct
    assert event_call.center_label == metadata["center_label"], (
        f"Expected center_label '{metadata['center_label']}', "
        f"got '{event_call.center_label}'"
    )
    assert event_call.project_label == metadata["project_label"], (
        f"Expected project_label '{metadata['project_label']}', "
        f"got '{event_call.project_label}'"
    )
    assert event_call.gear_name == metadata["gear_name"], (
        f"Expected gear_name '{metadata['gear_name']}', got '{event_call.gear_name}'"
    )
    assert event_call.timestamp == metadata["timestamp"], (
        f"Expected timestamp '{metadata['timestamp']}', got '{event_call.timestamp}'"
    )
    assert event_call.datatype == "form", (
        f"Expected datatype 'form', got '{event_call.datatype}'"
    )
    assert event_call.packet == csv_row["packet"], (
        f"Expected packet '{csv_row['packet']}', got '{event_call.packet}'"
    )

    # Verify other required fields from CSV are correctly extracted
    assert event_call.ptid == csv_row["ptid"], (
        f"Expected ptid '{csv_row['ptid']}', got '{event_call.ptid}'"
    )
    assert event_call.module == csv_row["module"].upper(), (
        f"Expected module '{csv_row['module'].upper()}', got '{event_call.module}'"
    )
    assert event_call.action == "submit", (
        f"Expected action 'submit', got '{event_call.action}'"
    )
    assert event_call.visit_number == csv_row["visitnum"], (
        f"Expected visit_number '{csv_row['visitnum']}', "
        f"got '{event_call.visit_number}'"
    )
    assert event_call.visit_date == csv_row["visitdate"], (
        f"Expected visit_date '{csv_row['visitdate']}', got '{event_call.visit_date}'"
    )
    assert event_call.pipeline_adcid == int(csv_row["adcid"]), (
        f"Expected pipeline_adcid {int(csv_row['adcid'])}, "
        f"got {event_call.pipeline_adcid}"
    )


@given(
    csv_rows=st.lists(valid_csv_row(), min_size=1, max_size=5),
    metadata=event_metadata(),
)
def test_property_multiple_events_metadata_correctness(csv_rows, metadata):
    """Property: For any collection of submit events created from multiple CSV rows,
      each event should contain correct metadata while preserving row-specific data.

      **Feature: identifier-lookup-event-logging,
    Property 5: Event Metadata Correctness**
      **Validates: Requirements 2.2, 2.4, 2.5, 2.6**
    """
    # Arrange - Create identifiers for all PTIDs
    identifiers = {}
    for row in csv_rows:
        identifiers[row["ptid"]] = IdentifierObject(
            ptid=row["ptid"],
            naccid=f"NACC{hash(row['ptid']) % 1000000:06d}",
            adcid=int(row["adcid"]),
            guid=None,
            naccadc=int(row["adcid"]) * 1000,
        )

    # Mock dependencies
    mock_qc_creator = Mock()
    mock_qc_creator.update_qc_log.return_value = True

    mock_event_logger = Mock(spec=VisitEventLogger)

    # Create visitors
    error_writer = ListErrorWriter(container_id="test", fw_path="test/path")
    output_stream = StringIO()

    identifier_visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="uds",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
        misc_errors=[],
        validator=None,
    )

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=Mock(),
        qc_log_creator=mock_qc_creator,
        gear_name=metadata["gear_name"],
        error_writer=error_writer,
        module_name="uds",
    )

    event_visitor = CSVLoggingVisitor(
        center_label=metadata["center_label"],
        project_label=metadata["project_label"],
        gear_name=metadata["gear_name"],
        event_logger=mock_event_logger,
        module_configs=uds_ingest_configs(),
        error_writer=error_writer,
        timestamp=metadata["timestamp"],
        action="submit",
        datatype="form",
    )

    # Create aggregate visitor
    aggregate_visitor = AggregateCSVVisitor(
        visitors=[identifier_visitor, qc_visitor, event_visitor],
        strategy_builder=visit_all_strategy,
    )

    # Act - Process all CSV rows
    header = ["ptid", "adcid", "module", "packet", "visitnum", "visitdate", "formver"]
    aggregate_visitor.visit_header(header)

    for line_num, row in enumerate(csv_rows, start=1):
        aggregate_visitor.visit_row(row, line_num)

    # Assert - Verify metadata correctness for all events
    assert mock_event_logger.log_event.call_count == len(csv_rows)

    for i, call in enumerate(mock_event_logger.log_event.call_args_list):
        event_call = call[0][0]
        assert isinstance(event_call, VisitEvent)

        # Verify shared metadata is consistent across all events
        assert event_call.center_label == metadata["center_label"]
        assert event_call.project_label == metadata["project_label"]
        assert event_call.gear_name == metadata["gear_name"]
        assert event_call.timestamp == metadata["timestamp"]
        assert event_call.datatype == "form"
        assert event_call.action == "submit"

        # Verify row-specific data is correctly extracted
        corresponding_row = csv_rows[i]
        assert event_call.packet == corresponding_row["packet"]
        assert event_call.ptid == corresponding_row["ptid"]
        assert event_call.module == corresponding_row["module"].upper()
        assert event_call.visit_number == corresponding_row["visitnum"]
        assert event_call.visit_date == corresponding_row["visitdate"]
        assert event_call.pipeline_adcid == int(corresponding_row["adcid"])
