"""Tests for EnrollmentFormVisitor output writing.

Demonstrates that writing QC-passed rows to the output CSV raises a
ValueError because the row dict contains keys (module, row_number) that
are not in the CSVWriter's fieldnames.
"""

from io import StringIO
from typing import Any, Dict, Optional

import pytest
from form_qc_app.enrollment import EnrollmentFormVisitor
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


def test_visit_row_raises_on_extra_fields_in_output():
    """When a row passes validation and is written to the output stream, the
    CSVWriter raises ValueError because 'module' and 'row_number' are added to
    the row dict but are not in the header fieldnames."""
    error_writer = ListErrorWriter(container_id="test-container", fw_path="test/path")
    processor = StubProcessor()
    output_stream = StringIO()

    visitor = EnrollmentFormVisitor(
        required_fields={"ptid", "adcid", "frmdate_enrl"},
        date_field="frmdate_enrl",
        error_writer=error_writer,
        processor=processor,  # type: ignore[arg-type]
        validator=StubRecordValidator(),  # type: ignore[arg-type]
        output_stream=output_stream,
    )

    header = ["ptid", "adcid", "frmdate_enrl"]
    assert visitor.visit_header(header), "Header should be accepted"

    row = {
        "ptid": "12345",
        "adcid": "99",
        "frmdate_enrl": "2025-01-15",
    }

    with pytest.raises(ValueError, match="dict contains fields not in fieldnames"):
        visitor.visit_row(row=row, line_num=1)
