"""Backward compatibility tests for identifier lookup refactoring.

These tests capture the current behavior before refactoring to ensure
the refactored implementation produces identical results.
"""

import csv
from io import StringIO
from typing import Any, Dict, List

import pytest
from identifier_app.main import NACCIDLookupVisitor, run
from identifiers.model import IdentifierObject
from nacc_common.error_models import FileError
from outputs.error_writer import ListErrorWriter
from test_mocks.mock_configs import uds_ingest_configs


class TestBackwardCompatibility:
    """Tests to verify backward compatibility after refactoring."""

    @pytest.fixture(scope="function")
    def sample_data_stream(self):
        """Create a sample data stream for compatibility testing."""
        data: List[List[str | int]] = [
            ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver", "var1"],
            [1, "PTID001", "2024-01-15", "1", "I", "4.0", 8],
            [1, "PTID002", "2024-01-16", "1", "I", "4.0", 99],
            [1, "PTID999", "2024-01-17", "1", "I", "4.0", 42],  # No matching ID
        ]
        stream = StringIO()
        writer = csv.writer(
            stream,
            delimiter=",",
            quotechar='"',
            quoting=csv.QUOTE_NONNUMERIC,
            lineterminator="\n",
        )
        writer.writerows(data)
        stream.seek(0)
        return stream

    @pytest.fixture(scope="function")
    def sample_identifiers_map(self):
        """Create identifiers map for compatibility testing."""
        id_map = {}
        id_map["PTID001"] = IdentifierObject(
            naccid="NACC000001", adcid=1, ptid="PTID001", guid=None, naccadc=1111
        )
        id_map["PTID002"] = IdentifierObject(
            naccid="NACC000002", adcid=1, ptid="PTID002", guid=None, naccadc=2222
        )
        return id_map

    def capture_current_behavior(
        self, input_stream: StringIO, identifiers_map: Dict[str, IdentifierObject]
    ) -> Dict[str, Any]:
        """Capture the current behavior of NACCIDLookupVisitor for comparison.

        Returns:
            Dictionary containing output CSV content, errors, and success status
        """
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
                misc_errors=misc_errors,
            ),
            error_writer=error_writer,
        )

        # Capture output CSV content
        out_stream.seek(0)
        output_content = out_stream.getvalue()

        # Parse CSV output for detailed comparison
        out_stream.seek(0)
        output_rows = []
        if output_content:
            reader = csv.DictReader(out_stream)
            output_rows = list(reader)

        return {
            "success": success,
            "output_content": output_content,
            "output_rows": output_rows,
            "errors": error_writer.errors().model_dump()
            if error_writer.errors()
            else None,
            "misc_errors": [error.model_dump() for error in misc_errors],
        }

    def test_baseline_behavior_mixed_success_failure(
        self, sample_data_stream, sample_identifiers_map
    ):
        """Test baseline behavior with mixed success and failure cases.

        This test captures the current behavior before refactoring.
        After refactoring, the new implementation should produce
        identical results.
        """
        baseline_result = self.capture_current_behavior(
            sample_data_stream, sample_identifiers_map
        )

        # Document expected behavior
        assert baseline_result["success"] is False  # Should fail due to PTID999
        assert baseline_result["output_content"] != ""  # Should have some output
        assert len(baseline_result["output_rows"]) == 2  # Two successful rows
        assert baseline_result["errors"] is not None  # Should have errors

        # Verify successful rows have NACCID and MODULE fields
        for row in baseline_result["output_rows"]:
            assert "naccid" in row
            assert "module" in row
            assert row["module"] == "uds"

        # Verify specific NACCIDs
        assert baseline_result["output_rows"][0]["naccid"] == "NACC000001"
        assert baseline_result["output_rows"][1]["naccid"] == "NACC000002"

        # Store baseline for future comparison
        self._baseline_result = baseline_result

    def test_error_structure_compatibility(
        self, sample_data_stream, sample_identifiers_map
    ):
        """Test that error structure remains compatible after refactoring."""
        result = self.capture_current_behavior(
            sample_data_stream, sample_identifiers_map
        )

        # Verify error structure
        assert result["errors"] is not None
        errors = result["errors"]

        # errors should be a list of error objects
        assert isinstance(errors, list)

        # Should have at least one error for PTID999
        assert len(errors) > 0

        # Verify error format
        first_error = errors[0]
        assert "message" in first_error
        assert "value" in first_error
        # Line number is stored in location.line
        assert "location" in first_error
        if first_error["location"]:
            assert "line" in first_error["location"]

    def test_header_validation_compatibility(self):
        """Test header validation behavior remains compatible."""
        # Test with missing required fields
        invalid_data: list[list[Any]] = [["dummy1", "dummy2", "dummy3"], [1, 2, 3]]
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerows(invalid_data)
        stream.seek(0)

        result = self.capture_current_behavior(stream, {})

        assert result["success"] is False
        assert result["output_content"] == ""
        assert result["errors"] is not None

    def test_fixture_based_regression(self):
        """Test using fixture files to verify exact output compatibility.

        This test uses the sample_input.csv and expected_output.csv
        fixtures to verify that the refactored implementation produces
        identical output.
        """
        # Create identifiers map matching the fixture data
        identifiers_map = {
            "PTID001": IdentifierObject(
                naccid="NACC000001", adcid=1, ptid="PTID001", guid=None, naccadc=1111
            ),
            "PTID002": IdentifierObject(
                naccid="NACC000002", adcid=1, ptid="PTID002", guid=None, naccadc=2222
            ),
        }

        # Create input stream matching fixture data
        data: List[List[str | int]] = [
            ["adcid", "ptid", "visitdate", "visitnum", "packet", "formver", "var1"],
            [1, "PTID001", "2024-01-15", "1", "I", "4.0", 8],
            [1, "PTID002", "2024-01-16", "1", "I", "4.0", 99],
            [1, "PTID999", "2024-01-17", "1", "I", "4.0", 42],  # No matching ID
        ]
        stream = StringIO()
        writer = csv.writer(
            stream,
            delimiter=",",
            quotechar='"',
            quoting=csv.QUOTE_NONNUMERIC,
            lineterminator="\n",
        )
        writer.writerows(data)
        stream.seek(0)

        # Process input
        result = self.capture_current_behavior(stream, identifiers_map)

        # Verify output matches expected
        assert result["success"] is False  # PTID999 has no match
        assert len(result["output_rows"]) == 2  # Two successful rows

        # Expected output structure
        expected_rows = [
            {
                "adcid": "1",
                "ptid": "PTID001",
                "visitdate": "2024-01-15",
                "visitnum": "1",
                "packet": "I",
                "formver": "4.0",
                "var1": "8",
                "naccid": "NACC000001",
                "module": "uds",
            },
            {
                "adcid": "1",
                "ptid": "PTID002",
                "visitdate": "2024-01-16",
                "visitnum": "1",
                "packet": "I",
                "formver": "4.0",
                "var1": "99",
                "naccid": "NACC000002",
                "module": "uds",
            },
        ]

        # Compare each row
        assert len(result["output_rows"]) == len(expected_rows)
        for actual_row, expected_row in zip(
            result["output_rows"], expected_rows, strict=False
        ):
            # Compare all fields
            for key in expected_row:
                assert actual_row[key] == expected_row[key], (
                    f"Mismatch in field {key}: {actual_row[key]} != {expected_row[key]}"
                )

    def test_output_csv_format_compatibility(
        self, sample_data_stream, sample_identifiers_map
    ):
        """Test that output CSV format (headers, field order) remains
        compatible."""
        result = self.capture_current_behavior(
            sample_data_stream, sample_identifiers_map
        )

        # Verify output has expected structure
        assert len(result["output_rows"]) > 0

        # Check that all original fields are preserved
        first_row = result["output_rows"][0]
        expected_fields = [
            "adcid",
            "ptid",
            "visitdate",
            "visitnum",
            "packet",
            "formver",
            "var1",
            "naccid",
            "module",
        ]

        for field in expected_fields:
            assert field in first_row, f"Expected field {field} not in output"

    def test_error_line_numbers_compatibility(
        self, sample_data_stream, sample_identifiers_map
    ):
        """Test that error line numbers are reported correctly."""
        result = self.capture_current_behavior(
            sample_data_stream, sample_identifiers_map
        )

        # Should have error for PTID999
        assert result["errors"] is not None
        errors = result["errors"]
        assert len(errors) > 0

        # Verify error has location information
        error_with_location = [e for e in errors if e.get("location")]
        assert len(error_with_location) > 0

        # Verify that at least one error has a line number
        # The exact line number depends on CSV reader implementation
        # but should be present for identifier lookup errors
        line_numbers = [
            e.get("location", {}).get("line")
            for e in errors
            if e.get("location") and e.get("location", {}).get("line")
        ]
        assert len(line_numbers) > 0, "Expected at least one error with line number"
        # Line numbers should be reasonable (between 1 and 10 for our test data)
        assert all(1 <= line_num <= 10 for line_num in line_numbers), (
            f"Line numbers out of expected range: {line_numbers}"
        )
