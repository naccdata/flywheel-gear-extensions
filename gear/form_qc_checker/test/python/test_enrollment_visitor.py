"""Tests for EnrollmentFormVisitor.

Covers:
- Bug: writing QC-passed rows raises ValueError due to extra fields
- Side effect: visit_row mutates the caller's row dict
"""

from io import StringIO
from typing import Any, Dict, Optional

import pytest
from form_qc_app.enrollment import EnrollmentFormVisitor
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter


class StubProcessor:
    """Minimal stand-in for CSVFileProcessor.

    Only implements update_visit_error_log so the visitor can call it
    without needing Flywheel connections or project adaptors.
    """

    def update_visit_error_log(
        self,
        *,
        input_record: Dict[str, Any],
        qc_passed: bool,
        reset_qc_metadata: str = "NA",
    ) -> bool:
        return True


class StubRecordValidator:
    """Minimal stand-in for RecordValidator.

    Always returns True so the visitor reaches the output-writing path.
    """

    def get_validation_schema(self) -> Dict:
        return {
            "ptid": {},
            "adcid": {},
            "frmdate_enrl": {},
        }

    def process_data_record(
        self, *, record: Dict[str, str], line_number: Optional[int] = None
    ) -> bool:
        return True


class FailingRecordValidator:
    """Stand-in for RecordValidator that always fails validation."""

    def get_validation_schema(self) -> Dict:
        return {
            "ptid": {},
            "adcid": {},
            "frmdate_enrl": {},
        }

    def process_data_record(
        self, *, record: Dict[str, str], line_number: Optional[int] = None
    ) -> bool:
        return False


REQUIRED_FIELDS = {"ptid", "adcid", "frmdate_enrl"}
HEADER = ["ptid", "adcid", "frmdate_enrl"]


def _make_visitor(
    *,
    validator: Optional[object] = None,
    output_stream: Optional[StringIO] = None,
) -> tuple[EnrollmentFormVisitor, ListErrorWriter, StubProcessor]:
    """Create an EnrollmentFormVisitor with common defaults."""
    error_writer = ListErrorWriter(container_id="test-container", fw_path="test/path")
    processor = StubProcessor()
    visitor = EnrollmentFormVisitor(
        required_fields=REQUIRED_FIELDS,
        date_field="frmdate_enrl",
        error_writer=error_writer,
        processor=processor,  # type: ignore[arg-type]
        validator=validator,  # type: ignore[arg-type]
        output_stream=output_stream,
    )
    return visitor, error_writer, processor


def _make_row(**overrides: str) -> Dict[str, str]:
    """Create a valid enrollment row with optional overrides."""
    row: Dict[str, str] = {
        "ptid": "12345",
        "adcid": "99",
        "frmdate_enrl": "2025-01-15",
    }
    row.update(overrides)
    return row


def test_visit_row_raises_on_extra_fields_in_output():
    """When a row passes validation and is written to the output stream, the
    CSVWriter raises ValueError because 'module' and 'row_number' are added to
    the row dict but are not in the header fieldnames."""
    output_stream = StringIO()
    visitor, _, _ = _make_visitor(
        validator=StubRecordValidator(),
        output_stream=output_stream,
    )

    assert visitor.visit_header(HEADER), "Header should be accepted"

    row = _make_row()
    with pytest.raises(ValueError, match="dict contains fields not in fieldnames"):
        visitor.visit_row(row=row, line_num=1)


def test_visit_row_mutates_row_with_module_on_success():
    """visit_row injects MODULE into the caller's row dict even when no output
    stream is provided (no write attempted)."""
    visitor, _, _ = _make_visitor(validator=StubRecordValidator())

    assert visitor.visit_header(HEADER)

    row = _make_row()
    original_keys = set(row.keys())

    # Without an output stream the write is skipped, so no ValueError
    visitor.visit_row(row=row, line_num=1)

    assert FieldNames.MODULE in row, (
        "MODULE should be injected into the row dict as a side effect"
    )
    assert set(row.keys()) - original_keys == {FieldNames.MODULE}


def test_visit_row_mutates_row_with_module_on_failure():
    """visit_row injects MODULE into the caller's row dict even when the row
    fails validation (missing required fields)."""
    visitor, _, _ = _make_visitor(validator=StubRecordValidator())

    assert visitor.visit_header(HEADER)

    # Row missing the required 'adcid' field
    row: Dict[str, Any] = {"ptid": "12345", "frmdate_enrl": "2025-01-15"}

    result = visitor.visit_row(row=row, line_num=1)

    assert result is False
    assert FieldNames.MODULE in row, (
        "MODULE is injected even when the row fails required-field checks"
    )


def test_visit_row_mutates_row_with_module_on_validator_failure():
    """visit_row injects MODULE into the caller's row dict even when the
    RecordValidator rejects the record."""
    visitor, _, _ = _make_visitor(validator=FailingRecordValidator())

    assert visitor.visit_header(HEADER)

    row = _make_row()
    result = visitor.visit_row(row=row, line_num=1)

    assert result is False
    assert FieldNames.MODULE in row, (
        "MODULE is injected even when the validator rejects the record"
    )
    # ROW_NUMBER should NOT be added because the record didn't pass
    assert FieldNames.ROW_NUMBER not in row
