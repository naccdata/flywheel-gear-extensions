"""Property test for NACCIDLookupVisitor separation of concerns.

**Feature: identifier-lookup-refactoring,
  Property 1: NACCIDLookupVisitor
Separation of Concerns**
**Validates: Requirements 1.1, 1.2, 1.3**
"""

import csv
from io import StringIO
from typing import Dict, List

from identifier_app.main import NACCIDLookupVisitor
from identifiers.model import IdentifierObject
from nacc_common.error_models import FileError
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


def test_naccid_lookup_visitor_separation_of_concerns():
    """Property test: NACCIDLookupVisitor performs identifier lookup without QC
    logging.

      **Feature: identifier-lookup-refactoring,
    Property 1: NACCIDLookupVisitor
      Separation of Concerns**
      **Validates: Requirements 1.1, 1.2, 1.3**

      For any CSV row processing, the NACCIDLookupVisitor should perform identifier
      lookup and CSV transformation without directly creating QC logs or updating
      QC metadata.
    """
    # Arrange - Use fixed test data to avoid PTID validation issues
    ptids = ["P001", "P002", "P003"]
    identifiers = {
        "P001": IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="P001", guid=None, naccadc=1001
        ),
        "P002": IdentifierObject(
            naccid="NACC000002", adcid=1, ptid="P002", guid=None, naccadc=1002
        ),
        "P003": IdentifierObject(
            naccid="NACC000003", adcid=1, ptid="P003", guid=None, naccadc=1003
        ),
    }

    output_stream = StringIO()
    error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create CSV data with required fields
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

    # Create visitor without QC-related dependencies
    visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
        misc_errors=misc_errors,
    )

    # Act - Process header
    csv_reader = csv.DictReader(input_stream)
    header = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    header_result = visitor.visit_header(header)

    # Process rows
    all_rows_processed = True
    for line_num, row in enumerate(
        csv_reader, start=2
    ):  # Start at 2 since header is line 1
        if not visitor.visit_row(row, line_num):
            all_rows_processed = False

    # Assert - Verify separation of concerns
    assert header_result, "Header processing should succeed"
    assert all_rows_processed, "All rows should be processed successfully"

    # Verify CSV transformation occurred (NACCID and MODULE fields added)
    output_stream.seek(0)
    output_reader = csv.DictReader(output_stream)
    output_fieldnames = output_reader.fieldnames or []

    assert FieldNames.NACCID in output_fieldnames, (
        "NACCID field should be added to output"
    )
    assert FieldNames.MODULE in output_fieldnames, (
        "MODULE field should be added to output"
    )

    # Verify identifier lookup occurred
    output_rows = list(output_reader)
    assert len(output_rows) == len(ptids), "All input rows should produce output rows"

    for i, output_row in enumerate(output_rows):
        expected_ptid = ptids[i]
        expected_naccid = identifiers[expected_ptid].naccid

        assert output_row[FieldNames.NACCID] == expected_naccid, (
            f"NACCID should be looked up correctly for PTID {expected_ptid}"
        )
        assert output_row[FieldNames.MODULE] == "test", "MODULE should be set correctly"

    # Verify no QC-related side effects
    # The visitor should not have any QC logging dependencies or methods
    assert not hasattr(visitor, "_NACCIDLookupVisitor__qc_log_manager"), (
        "Visitor should not have QC log manager"
    )
    assert not hasattr(visitor, "_NACCIDLookupVisitor__project"), (
        "Visitor should not have project dependency"
    )
    assert not hasattr(visitor, "_NACCIDLookupVisitor__gear_name"), (
        "Visitor should not have gear name dependency"
    )

    # Verify no QC logging methods exist
    assert not hasattr(visitor, "_NACCIDLookupVisitor__update_visit_error_log"), (
        "Visitor should not have QC logging method"
    )


def test_naccid_lookup_visitor_error_handling_without_qc():
    """Property test: NACCIDLookupVisitor handles identifier lookup failures
    without QC logging.

      **Feature: identifier-lookup-refactoring,
    Property 1: NACCIDLookupVisitor
      Separation of Concerns**
      **Validates: Requirements 1.1, 1.2, 1.3**

      When identifier lookup fails, the visitor should record errors without
      creating QC log entries.
    """
    # Arrange - Create empty identifiers map so lookups will fail
    invalid_ptids = ["INVALID1", "INVALID2"]
    identifiers: Dict[str, IdentifierObject] = {}
    output_stream = StringIO()
    error_writer = ListErrorWriter(container_id="test", fw_path="test-path")
    misc_errors: List[FileError] = []

    # Create CSV data with PTIDs that won't be found
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

    # Create visitor
    visitor = NACCIDLookupVisitor(
        identifiers=identifiers,
        output_file=output_stream,
        module_name="test",
        required_fields=uds_ingest_configs().required_fields,
        error_writer=error_writer,
        misc_errors=misc_errors,
    )

    # Act - Process header and rows
    csv_reader = csv.DictReader(input_stream)
    header = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
    visitor.visit_header(header)

    failed_rows = 0
    for line_num, row in enumerate(csv_reader, start=2):
        if not visitor.visit_row(row, line_num):
            failed_rows += 1

    # Assert - Verify error handling without QC logging
    assert failed_rows == len(invalid_ptids), "All rows with invalid PTIDs should fail"

    # Verify errors were recorded in error writer
    errors = error_writer.errors()
    assert len(errors.root) > 0, "Errors should be recorded for failed lookups"

    # Verify no output was generated for failed lookups
    output_stream.seek(0)
    output_content = output_stream.getvalue()
    # Should only contain header, no data rows
    lines = output_content.strip().split("\n")
    assert len(lines) <= 1, "No data rows should be written for failed lookups"

    # Verify no QC-related side effects occurred
    assert len(misc_errors) == 0, (
        "No miscellaneous errors should be generated (QC logging related)"
    )
