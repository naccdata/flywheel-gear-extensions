"""Unit tests for main.run function.

Tests cover the early-exit cases (no metadata, empty metadata, only
job_info) and the status determination with logging behavior.
"""

import logging
from unittest.mock import Mock

from dicom_qc_checker_app.main import run


def _make_file_entry(info: dict | None, name: str = "test_file.dcm") -> Mock:
    """Create a mock FileEntry with the given info dict."""
    file_entry = Mock()
    file_entry.info = info
    file_entry.name = name
    return file_entry


class TestRunNoMetadata:
    """Tests for cases where DICOM QC metadata is absent or empty."""

    def test_no_metadata_returns_none(self, caplog):
        """file.info has no qc key -> returns None, logs warning.

        Requirements: 1.2
        """
        file_entry = _make_file_entry(info={"some_key": "some_value"})

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result is None
        assert "No DICOM QC results available for file" in caplog.text
        assert "test_file.dcm" in caplog.text

    def test_none_info_returns_none(self, caplog):
        """file.info is None -> returns None, logs warning.

        Requirements: 1.2
        """
        file_entry = _make_file_entry(info=None)

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result is None
        assert "No DICOM QC results available for file" in caplog.text

    def test_empty_dicom_qc_returns_none(self, caplog):
        """file.info.qc.dicom-qc is {} -> returns None, logs warning.

        Requirements: 1.2
        """
        file_entry = _make_file_entry(info={"qc": {"dicom-qc": {}}})

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result is None
        assert "No DICOM QC results available for file" in caplog.text

    def test_only_job_info_returns_none(self, caplog):
        """Metadata has only job_info with no check results -> returns None.

        Requirements: 1.3
        """
        file_entry = _make_file_entry(
            info={
                "qc": {
                    "dicom-qc": {
                        "job_info": {
                            "job_id": "abc123",
                            "gear_name": "dicom-qc",
                        }
                    }
                }
            }
        )

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result is None
        assert "No DICOM QC check results available for file" in caplog.text
        assert "test_file.dcm" in caplog.text


class TestRunStatusDetermination:
    """Tests for status determination and logging behavior."""

    def test_single_pass_returns_pass(self, caplog):
        """One check with state PASS -> returns "PASS", no failure warnings.

        Requirements: 2.3, 2.4
        """
        file_entry = _make_file_entry(
            info={
                "qc": {
                    "dicom-qc": {
                        "job_info": {"job_id": "abc123"},
                        "slice_count_check": {"state": "PASS"},
                    }
                }
            }
        )

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result == "PASS"
        assert "failed or has invalid state" not in caplog.text

    def test_single_fail_returns_fail(self, caplog):
        """One check with state FAIL -> returns "FAIL", check name logged.

        Requirements: 2.3, 3.1, 3.2
        """
        file_entry = _make_file_entry(
            info={
                "qc": {
                    "dicom-qc": {
                        "job_info": {"job_id": "abc123"},
                        "slice_count_check": {"state": "FAIL"},
                    }
                }
            }
        )

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result == "FAIL"
        assert "slice_count_check" in caplog.text
        assert "failed or has invalid state" in caplog.text

    def test_mixed_results_returns_fail(self, caplog):
        """Multiple checks, some PASS some FAIL -> returns "FAIL".

        All failed check names should be logged at WARNING level.

        Requirements: 2.3, 2.4, 3.1, 3.2
        """
        file_entry = _make_file_entry(
            info={
                "qc": {
                    "dicom-qc": {
                        "job_info": {"job_id": "abc123"},
                        "slice_count_check": {"state": "PASS"},
                        "orientation_check": {"state": "FAIL"},
                        "pixel_spacing_check": {"state": "PASS"},
                        "modality_check": {"state": "FAIL"},
                    }
                }
            }
        )

        with caplog.at_level(logging.WARNING):
            result = run(file=file_entry)

        assert result == "FAIL"
        assert "orientation_check" in caplog.text
        assert "modality_check" in caplog.text
        # PASS checks should not be logged as failures
        assert "slice_count_check" not in caplog.text
        assert "pixel_spacing_check" not in caplog.text
