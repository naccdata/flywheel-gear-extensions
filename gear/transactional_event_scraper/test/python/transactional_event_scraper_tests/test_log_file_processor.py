"""Unit tests for log_file_processor module."""

from datetime import datetime

from event_capture.log_file_processor import (
    _extract_from_filename,
    extract_event_from_log,
)
from test_mocks.mock_flywheel import MockFile


class TestExtractFromFilename:
    """Tests for _extract_from_filename function."""

    def test_extract_from_valid_filename(self):
        """Test extraction from valid QC status log filename."""
        filename = "110001_2024-01-15_UDS_qc-status.log"
        metadata = _extract_from_filename(filename)

        assert metadata is not None
        assert metadata.ptid == "110001"
        assert metadata.date == "2024-01-15"
        assert metadata.module == "UDS"
        assert metadata.visitnum is None
        assert metadata.packet is None

    def test_extract_from_filename_lowercase_module(self):
        """Test extraction handles lowercase module names."""
        filename = "220002_2024-02-20_ftld_qc-status.log"
        metadata = _extract_from_filename(filename)

        assert metadata is not None
        assert metadata.ptid == "220002"
        assert metadata.date == "2024-02-20"
        assert metadata.module == "FTLD"  # Should be uppercased

    def test_extract_from_filename_special_chars_in_ptid(self):
        """Test extraction with special characters in PTID."""
        filename = "ABC-123_2024-03-30_LBD_qc-status.log"
        metadata = _extract_from_filename(filename)

        assert metadata is not None
        assert metadata.ptid == "ABC-123"
        assert metadata.date == "2024-03-30"
        assert metadata.module == "LBD"

    def test_extract_from_filename_invalid_pattern(self):
        """Test extraction returns None for invalid filename pattern."""
        invalid_filenames = [
            "not-a-qc-log.txt",
            "110001_2024-01-15_qc-status.log",  # Missing module
            "110001_UDS_qc-status.log",  # Missing date
            "2024-01-15_UDS_qc-status.log",  # Missing PTID
            "110001_2024-01-15_UDS.log",  # Wrong suffix
            "110001_2024-1-15_UDS_qc-status.log",  # Invalid date format
        ]

        for filename in invalid_filenames:
            metadata = _extract_from_filename(filename)
            assert metadata is None, f"Should return None for: {filename}"

    def test_extract_from_filename_max_ptid_length(self):
        """Test extraction with maximum PTID length (10 chars)."""
        filename = "1234567890_2024-04-15_UDS_qc-status.log"
        metadata = _extract_from_filename(filename)

        assert metadata is not None
        assert metadata.ptid == "1234567890"

    def test_extract_from_filename_ptid_too_long(self):
        """Test extraction fails when PTID exceeds 10 characters."""
        filename = "12345678901_2024-04-15_UDS_qc-status.log"
        metadata = _extract_from_filename(filename)

        assert metadata is None


class TestExtractEventFromLog:
    """Tests for extract_event_from_log function."""

    def test_extract_from_file_with_visit_metadata(self):
        """Test extraction from file with info.visit metadata (newer files)."""
        log_file = MockFile(
            name="110001_2024-01-15_UDS_qc-status.log",
            created=datetime(2024, 1, 15, 10, 0, 0),
            modified=datetime(2024, 1, 15, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                "visit": {
                    "ptid": "110001",
                    "date": "2024-01-15",
                    "visitnum": "001",
                    "module": "UDS",
                    "packet": "z1x",
                },
            },
        )

        event_data = extract_event_from_log(log_file)

        assert event_data is not None
        assert event_data.visit_metadata.ptid == "110001"
        assert event_data.visit_metadata.date == "2024-01-15"
        assert event_data.visit_metadata.visitnum == "001"
        assert event_data.visit_metadata.module == "UDS"
        assert event_data.visit_metadata.packet == "z1x"

    def test_extract_from_file_without_visit_metadata(self):
        """Test extraction from file without info.visit (older files).

        Falls back to filename.
        """
        log_file = MockFile(
            name="220002_2024-02-20_FTLD_qc-status.log",
            created=datetime(2024, 2, 20, 9, 0, 0),
            modified=datetime(2024, 2, 20, 10, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "FAIL", "data": []},
                    },
                },
                # No "visit" key - simulates older file
            },
        )

        event_data = extract_event_from_log(log_file)

        assert event_data is not None
        # Should extract from filename
        assert event_data.visit_metadata.ptid == "220002"
        assert event_data.visit_metadata.date == "2024-02-20"
        assert event_data.visit_metadata.module == "FTLD"
        # These fields not available from filename
        assert event_data.visit_metadata.visitnum is None
        assert event_data.visit_metadata.packet is None
        assert event_data.submission_timestamp == datetime(2024, 2, 20, 9, 0, 0)

    def test_extract_from_file_with_fail_status(self):
        """Test extraction with FAIL QC status."""
        log_file = MockFile(
            name="330003_2024-03-30_LBD_qc-status.log",
            created=datetime(2024, 3, 30, 14, 0, 0),
            modified=datetime(2024, 3, 30, 15, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "FAIL", "data": []},
                    },
                },
                "visit": {
                    "ptid": "330003",
                    "date": "2024-03-30",
                    "visitnum": "003",
                    "module": "LBD",
                    "packet": "a1",
                },
            },
        )

        event_data = extract_event_from_log(log_file)

        assert event_data is not None

    def test_extract_from_file_invalid_filename_no_metadata(self):
        """Test extraction fails when filename is invalid and no metadata
        present."""
        log_file = MockFile(
            name="invalid-filename.log",
            created=datetime(2024, 4, 15, 12, 0, 0),
            modified=datetime(2024, 4, 15, 13, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                # No "visit" key
            },
        )

        event_data = extract_event_from_log(log_file)

        # Should return None when both metadata and filename parsing fail
        assert event_data is None

    def test_extract_from_file_no_qc_metadata(self):
        """Test extraction when file has no QC metadata."""
        log_file = MockFile(
            name="440004_2024-04-15_UDS_qc-status.log",
            created=datetime(2024, 4, 15, 8, 0, 0),
            modified=datetime(2024, 4, 15, 9, 0, 0),
            info={
                "visit": {
                    "ptid": "440004",
                    "date": "2024-04-15",
                    "visitnum": "004",
                    "module": "UDS",
                    "packet": "z1x",
                },
                # No "qc" key
            },
        )

        event_data = extract_event_from_log(log_file)

        assert event_data is not None
        # Should still extract visit metadata
        assert event_data.visit_metadata.ptid == "440004"

    def test_extract_prioritizes_metadata_over_filename(self):
        """Test that info.visit metadata takes priority over filename
        parsing."""
        # Filename has different values than metadata
        log_file = MockFile(
            name="999999_2024-12-31_WRONG_qc-status.log",
            created=datetime(2024, 5, 15, 10, 0, 0),
            modified=datetime(2024, 5, 15, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                "visit": {
                    "ptid": "550005",
                    "date": "2024-05-15",
                    "visitnum": "005",
                    "module": "UDS",
                    "packet": "z1x",
                },
            },
        )

        event_data = extract_event_from_log(log_file)

        assert event_data is not None
        # Should use metadata values, not filename values
        assert event_data.visit_metadata.ptid == "550005"
        assert event_data.visit_metadata.date == "2024-05-15"
        assert event_data.visit_metadata.module == "UDS"
        assert event_data.visit_metadata.visitnum == "005"
        assert event_data.visit_metadata.packet == "z1x"

    def test_extract_from_file_with_empty_visit_dict(self):
        """Test extraction when visit dict exists but is empty."""
        log_file = MockFile(
            name="660006_2024-06-15_UDS_qc-status.log",
            created=datetime(2024, 6, 15, 10, 0, 0),
            modified=datetime(2024, 6, 15, 11, 0, 0),
            info={
                "qc": {
                    "form-qc-checker": {
                        "validation": {"state": "PASS", "data": []},
                    },
                },
                "visit": {},  # Empty dict
            },
        )

        event_data = extract_event_from_log(log_file)

        # Should fall back to filename parsing
        assert event_data is not None
        assert event_data.visit_metadata.ptid == "660006"
        assert event_data.visit_metadata.date == "2024-06-15"
        assert event_data.visit_metadata.module == "UDS"
