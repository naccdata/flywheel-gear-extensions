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
from test_mocks.mock_flywheel import MockProject


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
                gear_name="identifier-lookup",
                misc_errors=misc_errors,
                project=MockProject(label="test-project"),
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

        # Should have container_id and fw_path
        assert "container_id" in errors
        assert "fw_path" in errors
        assert "errors" in errors

        # Should have at least one error for PTID999
        assert len(errors["errors"]) > 0

        # Verify error format
        first_error = errors["errors"][0]
        assert "line" in first_error
        assert "message" in first_error
        assert "value" in first_error

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
