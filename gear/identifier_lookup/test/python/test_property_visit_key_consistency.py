"""Property test for visit key consistency.

**Feature: identifier-lookup-refactoring,
  Property 9: Visit Key Consistency**
**Validates: Requirements 2.5**
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
from nacc_common.error_models import FileError, VisitKeys
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


@st.composite
def visit_row_strategy(draw):
    """Generate random visit row data.

    Note: PTIDs are generated with uppercase letters and digits to avoid
    issues with clean_ptid() which strips leading zeros. PTIDs like "0" or "00"
    would become empty strings after cleaning.
    """
    ptid = draw(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Nd")),
        )
    )
    date = draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d")))
    visitnum = draw(st.integers(min_value=1, max_value=99).map(str))
    adcid = draw(st.integers(min_value=1, max_value=999))

    return {
        "ptid": ptid,
        "visitdate": date,
        "visitnum": visitnum,
        "adcid": adcid,
        "packet": "I",
        "formver": "4.0",
    }


@given(visit_row=visit_row_strategy())
@settings(max_examples=100)
def test_visit_keys_extracted_consistently(visit_row: Dict[str, str]):
    """Property test: VisitKeys are extracted consistently from CSV rows.

      **Feature: identifier-lookup-refactoring,
    Property 9: Visit Key Consistency**
      **Validates: Requirements 2.5**

      For any CSV row containing visit data, the system should use VisitKeys
      to identify visits consistently across all visitors.
    """
    # Arrange - Create QC visitor
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    # Act - Process row
    qc_visitor.visit_row(visit_row, line_num=1)

    # Assert - Verify VisitKeys were extracted and used
    assert mock_qc_creator.update_qc_log.called, "QC log should be created"

    call_kwargs = mock_qc_creator.update_qc_log.call_args[1]
    visit_keys = call_kwargs["visit_keys"]

    # Verify VisitKeys structure
    assert isinstance(visit_keys, VisitKeys), "visit_keys should be a VisitKeys object"

    # Verify VisitKeys contain consistent data from the row
    assert visit_keys.ptid == visit_row["ptid"], (
        f"VisitKeys PTID should match row data: "
        f"{visit_keys.ptid} != {visit_row['ptid']}"
    )
    assert visit_keys.date == visit_row["visitdate"], (
        f"VisitKeys date should match row data: "
        f"{visit_keys.date} != {visit_row['visitdate']}"
    )
    assert visit_keys.visitnum == visit_row["visitnum"], (
        f"VisitKeys visitnum should match row data: "
        f"{visit_keys.visitnum} != {visit_row['visitnum']}"
    )
    assert visit_keys.adcid == visit_row["adcid"], (
        f"VisitKeys ADCID should match row data: "
        f"{visit_keys.adcid} != {visit_row['adcid']}"
    )
    assert visit_keys.module == "TEST", (
        "VisitKeys module should be set from module_name parameter"
    )


@given(num_visits=st.integers(min_value=2, max_value=5))
@settings(max_examples=100)
def test_visit_keys_consistent_across_visitors(num_visits: int):
    """Property test: VisitKeys are consistent across multiple visitors.

      **Feature: identifier-lookup-refactoring,
    Property 9: Visit Key Consistency**
      **Validates: Requirements 2.5**

      For any CSV processing with multiple visitors, the system should use
      VisitKeys consistently to identify the same visit across all visitors.
    """
    # Arrange - Create CSV data with unique PTIDs
    # Note: Using "P###" format to avoid clean_ptid() stripping leading zeros
    csv_data = []
    for i in range(num_visits):
        csv_data.append(
            {
                "ptid": f"P{i:03d}",
                "visitdate": f"2024-01-{i + 1:02d}",
                "visitnum": str(i + 1),
                "adcid": 1,
                "packet": "I",
                "formver": "4.0",
            }
        )

    # Create identifiers for all PTIDs
    identifiers: Dict[str, IdentifierObject] = {}
    for i, visit in enumerate(csv_data):
        ptid: str = visit["ptid"]  # type: ignore[assignment]
        identifiers[ptid] = IdentifierObject(
            naccid=f"NACC{i:06d}",
            adcid=visit["adcid"],  # type: ignore[arg-type]
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

    # Assert - Verify VisitKeys are consistent across visitors
    processed_visits = qc_visitor.get_processed_visits()
    assert len(processed_visits) == len(csv_data), (
        "QC visitor should process all visits"
    )

    # Verify each processed visit has consistent VisitKeys
    for i, visit_keys in enumerate(processed_visits):
        expected_visit = csv_data[i]

        assert visit_keys.ptid == expected_visit["ptid"], (
            f"Visit {i}: PTID should be consistent: "
            f"{visit_keys.ptid} != {expected_visit['ptid']}"
        )
        assert visit_keys.date == expected_visit["visitdate"], (
            f"Visit {i}: date should be consistent: "
            f"{visit_keys.date} != {expected_visit['visitdate']}"
        )
        assert visit_keys.visitnum == expected_visit["visitnum"], (
            f"Visit {i}: visitnum should be consistent: "
            f"{visit_keys.visitnum} != {expected_visit['visitnum']}"
        )
        assert visit_keys.module == "TEST", f"Visit {i}: module should be consistent"

    # Verify QC log calls used the same VisitKeys
    qc_calls = mock_qc_creator.update_qc_log.call_args_list
    assert len(qc_calls) == len(csv_data), "QC log should be created for each visit"

    for i, call in enumerate(qc_calls):
        call_visit_keys = call[1]["visit_keys"]
        processed_visit_keys = processed_visits[i]

        # Verify the VisitKeys used in QC log call match the processed visit
        assert call_visit_keys.ptid == processed_visit_keys.ptid, (
            f"Visit {i}: QC log VisitKeys PTID should match processed visit"
        )
        assert call_visit_keys.date == processed_visit_keys.date, (
            f"Visit {i}: QC log VisitKeys date should match processed visit"
        )
        assert call_visit_keys.module == processed_visit_keys.module, (
            f"Visit {i}: QC log VisitKeys module should match processed visit"
        )


def test_visit_keys_with_missing_fields():
    """Test VisitKeys extraction with missing optional fields.

      **Feature: identifier-lookup-refactoring,
    Property 9: Visit Key Consistency**
      **Validates: Requirements 2.5**

      When CSV rows have missing optional fields, VisitKeys should still be
      extracted consistently with None values for missing fields.
    """
    # Arrange - Create QC visitor
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="test",
    )

    # Act - Process row with missing ADCID (optional field)
    visit_row = {
        "ptid": "P001",
        "visitdate": "2024-01-01",
        "visitnum": "1",
        "packet": "I",
        "formver": "4.0",
    }
    qc_visitor.visit_row(visit_row, line_num=1)

    # Assert - Verify VisitKeys were extracted with None for missing field
    assert mock_qc_creator.update_qc_log.called, "QC log should be created"

    call_kwargs = mock_qc_creator.update_qc_log.call_args[1]
    visit_keys = call_kwargs["visit_keys"]

    assert visit_keys.ptid == "P001", "VisitKeys should have PTID"
    assert visit_keys.date == "2024-01-01", "VisitKeys should have date"
    assert visit_keys.visitnum == "1", "VisitKeys should have visitnum"
    assert visit_keys.adcid is None, "VisitKeys should have None for missing ADCID"
    assert visit_keys.module == "TEST", "VisitKeys should have module"


def test_visit_keys_module_name_handling():
    """Test VisitKeys module name handling with and without module_name
    parameter.

      **Feature: identifier-lookup-refactoring,
    Property 9: Visit Key Consistency**
      **Validates: Requirements 2.5**

      When module_name is provided to QCStatusLogCSVVisitor, it should be used
      consistently in VisitKeys regardless of MODULE field in the row.
    """
    # Arrange - Create QC visitor with module_name parameter
    shared_error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    mock_project = Mock(spec=ProjectAdaptor)
    mock_qc_creator = Mock(spec=QCStatusLogManager)
    mock_qc_creator.update_qc_log.return_value = True

    qc_visitor = QCStatusLogCSVVisitor(
        module_configs=uds_ingest_configs(),
        project=mock_project,
        qc_log_creator=mock_qc_creator,
        gear_name="identifier-lookup",
        error_writer=shared_error_writer,
        module_name="custom_module",  # Explicit module name
    )

    # Act - Process row (MODULE field in row should be ignored)
    visit_row = {
        "ptid": "P001",
        "visitdate": "2024-01-01",
        "visitnum": "1",
        "adcid": 1,
        "module": "ignored_module",  # This should be ignored
        "packet": "I",
        "formver": "4.0",
    }
    qc_visitor.visit_row(visit_row, line_num=1)

    # Assert - Verify VisitKeys use the provided module_name
    call_kwargs = mock_qc_creator.update_qc_log.call_args[1]
    visit_keys = call_kwargs["visit_keys"]

    assert visit_keys.module == "CUSTOM_MODULE", (
        "VisitKeys should use module_name parameter (uppercased)"
    )
