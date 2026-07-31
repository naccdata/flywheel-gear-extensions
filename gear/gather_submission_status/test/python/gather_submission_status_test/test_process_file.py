"""Tests for _process_reloaded_file processing logic.

Validates: Requirements 2.1, 2.2, 3.3, 6.2 / Property 4: QC Validation Equivalence
"""

from typing import Any
from unittest.mock import Mock, patch

from gather_submission_status_app.main import _process_reloaded_file
from nacc_common.qc_report import (
    ListReportWriter,
    QCTransformerError,
    WriterTableVisitor,
)


def _create_mock_file_entry(
    name: str = "PT001_2024-01-15_UDS_qc-status.log",
    info: dict[str, Any] | None = None,
) -> Mock:
    """Create a mock FileEntry with .name and .info attributes."""
    file_entry = Mock()
    file_entry.name = name
    file_entry.info = info
    return file_entry


def _create_table_visitor() -> tuple[WriterTableVisitor, list[dict[str, Any]]]:
    """Create a WriterTableVisitor with ListReportWriter for assertions."""
    results: list[dict[str, Any]] = []
    writer = ListReportWriter(results)
    table_visitor = WriterTableVisitor(writer)
    return table_visitor, results


class TestProcessReloadedFileValid:
    """Tests for valid QC file processing."""

    def test_valid_qc_produces_report_rows(self) -> None:
        """A file with valid file.info.qc produces expected report rows via the
        table_visitor.

        **Validates: Requirements 2.1, 2.2**
        """
        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {
                        "state": "PASS",
                        "data": [],
                        "cleared": [],
                    }
                }
            }
        }
        file_entry = _create_mock_file_entry(info=file_info)
        table_visitor, results = _create_table_visitor()

        # Create a mock visitor with a populated table
        mock_report_row = Mock()
        mock_report_row.model_dump.return_value = {"col1": "val1", "col2": "val2"}

        mock_file_visitor = Mock()
        mock_file_visitor.visit_details = Mock()  # non-None
        mock_file_visitor.table = [mock_report_row]

        mock_builder = Mock(return_value=mock_file_visitor)

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 1
        assert results[0] == {"col1": "val1", "col2": "val2"}

    def test_file_visitor_builder_called_with_correct_args(self) -> None:
        """file_visitor_builder is called with correct (file, adcid) arguments.

        **Validates: Requirements 6.2**
        """
        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {
                        "state": "PASS",
                        "data": [],
                        "cleared": [],
                    }
                }
            }
        }
        file_entry = _create_mock_file_entry(info=file_info)
        table_visitor, _ = _create_table_visitor()

        mock_file_visitor = Mock()
        mock_file_visitor.visit_details = Mock()
        mock_file_visitor.table = []

        mock_builder = Mock(return_value=mock_file_visitor)
        adcid = 42

        _process_reloaded_file(
            file=file_entry,
            adcid=adcid,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        mock_builder.assert_called_once_with(file_entry, adcid)


class TestProcessReloadedFileSkipped:
    """Tests for files that should be skipped."""

    def test_file_without_info_skipped(self) -> None:
        """A file with info=None is skipped (logs warning, no rows written).

        **Validates: Requirements 3.3**
        """
        file_entry = _create_mock_file_entry(info=None)
        table_visitor, results = _create_table_visitor()
        mock_builder = Mock()

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0
        mock_builder.assert_not_called()

    def test_file_without_qc_key_skipped(self) -> None:
        """A file with info={} (no 'qc' key) is skipped.

        **Validates: Requirements 3.3**
        """
        file_entry = _create_mock_file_entry(info={"other": "data"})
        table_visitor, results = _create_table_visitor()
        mock_builder = Mock()

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0
        mock_builder.assert_not_called()

    def test_file_with_empty_qc_skipped(self) -> None:
        """A file with info={'qc': {}} (empty qc dict evaluating as falsy) is
        skipped.

        **Validates: Requirements 3.3**
        """
        file_entry = _create_mock_file_entry(info={"qc": {}})
        table_visitor, results = _create_table_visitor()
        mock_builder = Mock()

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0
        mock_builder.assert_not_called()

    def test_invalid_qc_data_validation_error_skipped(self) -> None:
        """A file with invalid QC data (ValidationError) is skipped (logs
        warning).

        **Validates: Requirements 3.3**
        """
        # Provide data that passes the guard (truthy 'qc' value) but fails
        # Pydantic validation — qc must be Dict[str, GearQCModel], not a string
        file_entry = _create_mock_file_entry(info={"qc": "not_a_dict"})
        table_visitor, results = _create_table_visitor()
        mock_builder = Mock()

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0
        mock_builder.assert_not_called()

    @patch("gather_submission_status_app.main.FileQCModel.model_validate")
    def test_qc_transformer_error_skipped(self, mock_validate: Mock) -> None:
        """A file causing QCTransformerError during apply is skipped (logs
        error).

        **Validates: Requirements 2.2**
        """
        mock_qc_model = Mock()
        mock_qc_model.apply.side_effect = QCTransformerError(
            "Unexpected transformation error"
        )
        mock_validate.return_value = mock_qc_model

        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {
                        "state": "PASS",
                        "data": [],
                        "cleared": [],
                    }
                }
            }
        }
        file_entry = _create_mock_file_entry(info=file_info)
        table_visitor, results = _create_table_visitor()

        mock_file_visitor = Mock()
        mock_file_visitor.visit_details = Mock()  # non-None
        mock_builder = Mock(return_value=mock_file_visitor)

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0

    def test_visit_details_none_skipped(self) -> None:
        """A file where the visitor has visit_details=None is skipped.

        **Validates: Requirements 3.3**
        """
        file_info = {
            "qc": {
                "form-qc-checker": {
                    "validation": {
                        "state": "PASS",
                        "data": [],
                        "cleared": [],
                    }
                }
            }
        }
        file_entry = _create_mock_file_entry(info=file_info)
        table_visitor, results = _create_table_visitor()

        mock_file_visitor = Mock()
        mock_file_visitor.visit_details = None  # Cannot extract visit details
        mock_builder = Mock(return_value=mock_file_visitor)

        _process_reloaded_file(
            file=file_entry,
            adcid=1,
            file_visitor_builder=mock_builder,
            table_visitor=table_visitor,
        )

        assert len(results) == 0
