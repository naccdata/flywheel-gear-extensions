"""Tests for ErrorWriter class."""

# pylint: disable=no-self-use,redefined-outer-name,too-few-public-methods
from csv import DictReader
from io import StringIO

from nacc_common.error_models import (
    CSVLocation,
    FileError,
    JSONLocation,
)
from outputs.error_writer import ListErrorWriter, StreamErrorWriter
from outputs.errors import (
    empty_file_error,
    identifier_error,
    missing_header_error,
)


class TestFileError:
    """Tests the FileError model class."""

    def test_serialization(self):
        """Tests that serialization produces a dict with the location a
        string."""
        error = FileError(
            error_type="error",  # pyright: ignore[reportCallIssue]
            error_code="the-error",  # pyright: ignore[reportCallIssue]
            location=JSONLocation(key_path="k1.k2.k3"),
            value="the-value",
            message="the-message",
        )
        result = error.model_dump(by_alias=True)
        assert isinstance(result, dict)
        assert "type" in result
        assert "code" in result
        assert "location" in result
        assert "flywheel_path" in result
        assert "container_id" in result
        assert "message" in result
        assert result["location"] == {"key_path": "k1.k2.k3"}
        assert result["type"] == "error"

    def test_identifier_serialization(self):
        """Tests that error created by identifier_error can be serialized."""
        error = identifier_error(line=11, value="dummy")
        assert error.model_dump()

    def test_empty_file_serialization(self):
        """Test that error created by empty_file_error can be serialized."""
        error = empty_file_error()
        assert error.model_dump()

    def test_missing_header_serialization(self):
        """Test that error created by missing_header_error can be
        serialized."""
        error = missing_header_error()
        assert error.model_dump()


class TestErrorWriter:
    """Tests the error writer class."""

    def test_fieldnames(self):
        """Checks that the FileError.fieldnames method returns the correct
        names."""
        fieldnames = FileError.fieldnames()
        assert "type" in fieldnames
        assert "code" in fieldnames
        assert "location" in fieldnames
        assert "container_id" in fieldnames
        assert "flywheel_path" in fieldnames
        assert "value" in fieldnames
        assert "expected" in fieldnames
        assert "message" in fieldnames

    def test_stream_write(self):
        """Tests that the stream error writer writes CSV with the flywheel
        hierarchy information inserted."""
        stream = StringIO()
        writer = StreamErrorWriter(
            stream=stream, container_id="the-id", fw_path="the-path"
        )
        writer.write(
            FileError(
                error_type="error",  # pyright: ignore[reportCallIssue]
                error_code="the-error",  # pyright: ignore[reportCallIssue]
                location=CSVLocation(line=10, column_name="ptid"),
                container_id=None,
                value="the-value",
                expected=None,
                message="the-message",
                ptid="the-ptid",
                visitnum="the-visitnum",
                date="the-date",
                naccid="the-naccid",
            )
        )
        stream.seek(0)
        reader = DictReader(stream, dialect="unix")
        assert reader.fieldnames
        assert reader.fieldnames == list(FileError.fieldnames())
        row = next(reader)
        assert row["container_id"] == "the-id"

    def test_capture_write(self):
        """Tests that the capture error writer inserts the flywheel hierarchy
        information inserted."""
        writer = ListErrorWriter(container_id="the-id", fw_path="the-path")
        writer.write(
            FileError(
                error_type="error",  # pyright: ignore[reportCallIssue]
                error_code="the-error",  # pyright: ignore[reportCallIssue]
                location=CSVLocation(line=10, column_name="ptid"),
                container_id=None,
                value="the-value",
                expected=None,
                message="the-message",
            )
        )
        errors = writer.errors()
        assert errors[0].container_id == "the-id"
