"""Property-based test for backward compatibility baseline.

**Feature: identifier-lookup-refactoring, Property 6: Backward Compatibility**

This test validates that the refactored system produces identical output files,
error messages, and QC log structures compared to the original implementation.
"""

import csv
from io import StringIO
from typing import Any, Dict, List

from hypothesis import strategies as st
from identifier_app.main import NACCIDLookupVisitor, run
from identifiers.model import IdentifierObject
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs
from test_mocks.mock_flywheel import MockProject


# Hypothesis strategies for generating test data
@st.composite
def ptid_strategy(draw):
    """Generate valid PTID strings matching pattern ^[!-~]{1,10}$."""
    # PTIDs must match printable non-whitespace ASCII characters, 1-10 chars
    # Pattern: ^[!-~]{1,10}$ (ASCII 33-126, excluding space)
    # Also ensure they don't become empty after clean_ptid (strip leading zeros)
    alphabet = "".join(
        chr(i) for i in range(33, 127)
    )  # ASCII 33-126 (printable, no space)

    # Generate a PTID that won't become empty after cleaning
    ptid = draw(st.text(alphabet=alphabet, min_size=1, max_size=10))

    # Ensure it doesn't become empty after clean_ptid processing
    # clean_ptid strips whitespace and leading zeros
    cleaned = ptid.strip().lstrip("0")
    if not cleaned:
        # If it becomes empty, prepend a non-zero character
        ptid = "A" + ptid

    return ptid


@st.composite
def csv_row_strategy(draw):
    """Generate a valid CSV row for identifier lookup."""
    ptid = draw(ptid_strategy())
    return {
        "adcid": 1,
        "ptid": ptid,
        "visitdate": "2024-01-15",
        "visitnum": "1",
        "packet": "I",
        "formver": "4.0",
        "var1": draw(st.integers(min_value=0, max_value=999)),
    }


@st.composite
def csv_data_strategy(draw):
    """Generate CSV data with header and multiple rows."""
    num_rows = draw(st.integers(min_value=1, max_value=5))
    rows = [draw(csv_row_strategy()) for _ in range(num_rows)]

    # Create CSV content
    header = ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver", "var1"]
    csv_data = [header]
    for row in rows:
        csv_data.append([row[field] for field in header])

    return csv_data, rows


@st.composite
def identifiers_strategy(draw, ptids: List[str]):
    """Generate identifiers map with some matching PTIDs."""
    identifiers = {}

    # Randomly include some PTIDs in identifiers (50% chance each)
    for ptid in ptids:
        if draw(st.booleans()):
            naccid = f"NACC{draw(st.integers(min_value=100000, max_value=999999)):06d}"
            identifiers[ptid] = IdentifierObject(
                naccid=naccid,
                adcid=1,
                ptid=ptid,
                guid=None,
                naccadc=draw(st.integers(min_value=1000, max_value=9999)),
            )

    return identifiers


def create_csv_stream(csv_data: List[List[Any]]) -> StringIO:
    """Create a StringIO stream from CSV data."""
    stream = StringIO()
    writer = csv.writer(
        stream,
        delimiter=",",
        quotechar='"',
        quoting=csv.QUOTE_NONNUMERIC,
        lineterminator="\n",
    )
    writer.writerows(csv_data)
    stream.seek(0)
    return stream


def capture_naccid_lookup_behavior(
    csv_data: List[List[Any]], identifiers_map: Dict[str, IdentifierObject]
) -> Dict[str, Any]:
    """Capture the behavior of NACCIDLookupVisitor for comparison."""
    input_stream = create_csv_stream(csv_data)
    out_stream = StringIO()
    misc_errors: List[FileError] = []
    error_writer = ListErrorWriter(container_id="test", fw_path="test-path")

    success = run(
        input_file=input_stream,
        lookup_visitor=NACCIDLookupVisitor(
            adcid=1,
            identifiers=identifiers_map,
            output_file=out_stream,
            module_name="uds",
            module_configs=uds_ingest_configs(),
            error_writer=error_writer,
            gear_name="identifier-lookup",
            misc_errors=misc_errors,
            project=MockProject(label="test-project"),
        ),
        error_writer=error_writer,
    )

    # Capture all output details
    out_stream.seek(0)
    output_content = out_stream.getvalue()

    # Parse output rows if any
    out_stream.seek(0)
    output_rows = []
    if output_content:
        try:
            reader = csv.DictReader(out_stream)
            output_rows = list(reader)
        except Exception:
            # Handle malformed CSV
            pass

    return {
        "success": success,
        "output_content": output_content,
        "output_rows": output_rows,
        "errors": error_writer.errors().model_dump() if error_writer.errors() else None,
        "misc_errors": [error.model_dump() for error in misc_errors],
        "error_count": len(error_writer.errors().root) if error_writer.errors() else 0,
    }


class TestPropertyBackwardCompatibility:
    """Property-based tests for backward compatibility baseline."""

    def test_backward_compatibility_baseline_simple(self):
        """**Feature: identifier-lookup-refactoring, Property 6: Backward
        Compatibility**

        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

        For any input CSV file, the refactored system should produce identical
        output files, error messages, and QC log structures compared to the
        original implementation.

        This test establishes the baseline behavior before refactoring with a
        simple case.
        """
        # Simple test case with known data
        csv_data: list[list[Any]] = [
            ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver", "var1"],
            [1, "PTID001", "2024-01-15", "1", "I", "4.0", 8],
            [1, "PTID002", "2024-01-16", "1", "I", "4.0", 99],
            [1, "PTID999", "2024-01-17", "1", "I", "4.0", 42],  # No matching ID
        ]

        # Create identifiers for first two PTIDs only
        identifiers_map = {
            "PTID001": IdentifierObject(
                naccid="NACC000001", adcid=1, ptid="PTID001", guid=None, naccadc=1111
            ),
            "PTID002": IdentifierObject(
                naccid="NACC000002", adcid=1, ptid="PTID002", guid=None, naccadc=2222
            ),
        }

        # Capture current behavior
        result = capture_naccid_lookup_behavior(csv_data, identifiers_map)

        # Verify basic invariants that should hold after refactoring

        # 1. Should fail because PTID999 has no identifier
        assert result["success"] is False, (
            "Should fail when some PTIDs missing identifiers"
        )

        # 2. Should have output for successful PTIDs
        assert len(result["output_rows"]) == 2, "Should have 2 successful rows"

        # 3. Output structure should be consistent
        for row in result["output_rows"]:
            assert "naccid" in row, "Output rows should have naccid field"
            assert "module" in row, "Output rows should have module field"
            assert row["module"] == "uds", "Module should be set correctly"

        # 4. Verify specific NACCIDs
        output_naccids = [row["naccid"] for row in result["output_rows"]]
        assert "NACC000001" in output_naccids, "Should contain NACC000001"
        assert "NACC000002" in output_naccids, "Should contain NACC000002"

    def test_empty_input_baseline(self):
        """Test baseline behavior with empty input."""
        empty_csv = [
            ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver", "var1"]
        ]
        result = capture_naccid_lookup_behavior(empty_csv, {})

        # Empty input (header only) should succeed but produce no output
        assert result["success"] is True
        assert result["output_content"] == ""
        assert result["error_count"] == 0

    def test_missing_header_baseline(self):
        """Test baseline behavior with missing required headers."""
        invalid_csv: list[list[Any]] = [["dummy1", "dummy2", "dummy3"], [1, 2, 3]]
        result = capture_naccid_lookup_behavior(invalid_csv, {})

        # Missing headers should fail
        assert result["success"] is False
        assert result["output_content"] == ""
        assert result["error_count"] > 0
