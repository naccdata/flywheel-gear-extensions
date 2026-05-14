"""Tests for PTID filtering on get_error_data and get_status_data.

Verifies that the optional `ptids` parameter correctly filters results
by participant ID, maintains backward compatibility when omitted, and
works in combination with `modules` filtering.

Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 7.1, 7.2
"""

from unittest.mock import MagicMock, patch

from nacc_common.error_data import get_error_data, get_status_data


def _make_file_entry(ptid: str, date: str, module: str, qc_data: dict) -> MagicMock:
    """Create a mock FileEntry with a QC log filename and info.

    The file.info dict contains both the QC data and visit metadata matching
    the filename, which mirrors how real Flywheel files are structured.

    Args:
        ptid: participant identifier
        date: visit date (YYYY-MM-DD)
        module: module name (e.g. UDS, LBD)
        qc_data: dict representing QC data to place in file.info.qc

    Returns:
        MagicMock that behaves like a FileEntry for ProjectReportVisitor
    """
    filename = f"{ptid}_{date}_{module}_qc-status.log"
    file_entry = MagicMock()
    file_entry.name = filename
    file_entry.info = {"qc": qc_data}
    file_entry.reload.return_value = file_entry
    return file_entry


def _make_project(files: list, adcid: int = 42) -> MagicMock:
    """Create a mock Project with file entries and pipeline ADCID.

    Args:
        files: list of mock FileEntry objects
        adcid: pipeline ADCID value

    Returns:
        MagicMock that behaves like a flywheel Project
    """
    project = MagicMock()
    project.files = files
    project.info = {"pipeline_adcid": adcid}
    project.label = "test-project"
    project.reload.return_value = project
    return project


def _qc_with_errors(ptid: str) -> dict:
    """Return a QC data structure with one gear that has one error.

    The error includes the ptid so that the serialized error record
    identifies which participant the error belongs to.

    Args:
        ptid: participant identifier to embed in the error
    """
    return {
        "form_qc_checker": {
            "validation": {
                "state": "FAIL",
                "data": [
                    {
                        "type": "error",
                        "code": "VAL001",
                        "message": "validation failed",
                        "ptid": ptid,
                    }
                ],
                "cleared": [],
            }
        }
    }


def _qc_passing() -> dict:
    """Return a QC data structure with one gear that passes."""
    return {
        "form_qc_checker": {
            "validation": {
                "state": "PASS",
                "data": [],
                "cleared": [],
            }
        }
    }


class TestGetErrorDataPtidFilter:
    """Tests for PTID filtering on get_error_data."""

    def test_ptids_filters_to_matching_only(self):
        """Calling with ptids returns errors only for matching PTIDs.

        Validates: Requirements 1.1
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_with_errors("PT001")),
            _make_file_entry("PT002", "2024-01-16", "UDS", _qc_with_errors("PT002")),
            _make_file_entry("PT003", "2024-01-17", "UDS", _qc_with_errors("PT003")),
        ]
        project = _make_project(files)

        result = get_error_data(project, ptids={"PT001", "PT003"})

        ptids_in_result = {row["ptid"] for row in result}
        assert ptids_in_result == {"PT001", "PT003"}
        assert "PT002" not in ptids_in_result

    def test_no_ptids_returns_all(self):
        """Calling without ptids returns errors for all submissions.

        Validates: Requirements 1.2, 7.1
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_with_errors("PT001")),
            _make_file_entry("PT002", "2024-01-16", "UDS", _qc_with_errors("PT002")),
            _make_file_entry("PT003", "2024-01-17", "UDS", _qc_with_errors("PT003")),
        ]
        project = _make_project(files)

        result = get_error_data(project)

        ptids_in_result = {row["ptid"] for row in result}
        assert ptids_in_result == {"PT001", "PT002", "PT003"}

    def test_modules_and_ptids_applies_both_filters(self):
        """Calling with both modules and ptids applies both filters.

        Validates: Requirements 1.3
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_with_errors("PT001")),
            _make_file_entry("PT001", "2024-01-16", "LBD", _qc_with_errors("PT001")),
            _make_file_entry("PT002", "2024-01-17", "UDS", _qc_with_errors("PT002")),
            _make_file_entry("PT002", "2024-01-18", "LBD", _qc_with_errors("PT002")),
        ]
        project = _make_project(files)

        result = get_error_data(project, modules={"UDS"}, ptids={"PT001"})

        assert len(result) == 1
        assert result[0]["ptid"] == "PT001"
        assert result[0]["module"] == "UDS"

    def test_backward_compatible_with_modules_only(self):
        """Calling with only modules (no ptids) works as before.

        Validates: Requirements 7.1
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_with_errors("PT001")),
            _make_file_entry("PT001", "2024-01-16", "LBD", _qc_with_errors("PT001")),
        ]
        project = _make_project(files)

        result = get_error_data(project, modules={"UDS"})

        assert len(result) == 1
        assert result[0]["module"] == "UDS"

    def test_empty_ptids_set_returns_nothing(self):
        """Calling with an empty ptids set returns no results."""
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_with_errors("PT001")),
        ]
        project = _make_project(files)

        result = get_error_data(project, ptids=set())

        assert result == []


class TestGetStatusDataPtidFilter:
    """Tests for PTID filtering on get_status_data.

    These tests verify that ptids is correctly wired through to
    ProjectReportVisitor as ptid_set.
    """

    def test_ptids_passed_to_visitor(self):
        """The ptids parameter is passed through as ptid_set to
        ProjectReportVisitor.

        Validates: Requirements 2.1, 2.2, 2.3
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_passing()),
            _make_file_entry("PT002", "2024-01-16", "UDS", _qc_passing()),
        ]
        project = _make_project(files)

        with patch("nacc_common.error_data.ProjectReportVisitor") as mock_visitor_cls:
            mock_visitor = MagicMock()
            mock_visitor_cls.return_value = mock_visitor

            get_status_data(project, ptids={"PT001"})

            mock_visitor_cls.assert_called_once()
            call_kwargs = mock_visitor_cls.call_args
            assert call_kwargs.kwargs["ptid_set"] == {"PT001"}

    def test_no_ptids_passes_none_to_visitor(self):
        """Calling without ptids passes None for ptid_set, preserving existing
        behavior.

        Validates: Requirements 2.2, 7.2
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_passing()),
        ]
        project = _make_project(files)

        with patch("nacc_common.error_data.ProjectReportVisitor") as mock_visitor_cls:
            mock_visitor = MagicMock()
            mock_visitor_cls.return_value = mock_visitor

            get_status_data(project)

            call_kwargs = mock_visitor_cls.call_args
            assert call_kwargs.kwargs["ptid_set"] is None

    def test_modules_and_ptids_both_passed(self):
        """Calling with both modules and ptids passes both to the visitor.

        Validates: Requirements 2.3
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_passing()),
        ]
        project = _make_project(files)

        with patch("nacc_common.error_data.ProjectReportVisitor") as mock_visitor_cls:
            mock_visitor = MagicMock()
            mock_visitor_cls.return_value = mock_visitor

            get_status_data(project, modules={"UDS"}, ptids={"PT001"})

            call_kwargs = mock_visitor_cls.call_args
            assert call_kwargs.kwargs["ptid_set"] == {"PT001"}
            assert call_kwargs.kwargs["modules"] == {"UDS"}

    def test_backward_compatible_without_ptids(self):
        """Existing call signature with only project works.

        Validates: Requirements 7.2
        """
        files = [
            _make_file_entry("PT001", "2024-01-15", "UDS", _qc_passing()),
        ]
        project = _make_project(files)

        with patch("nacc_common.error_data.ProjectReportVisitor") as mock_visitor_cls:
            mock_visitor = MagicMock()
            mock_visitor_cls.return_value = mock_visitor

            # Call with just project — should not raise
            get_status_data(project)

            mock_visitor_cls.assert_called_once()
