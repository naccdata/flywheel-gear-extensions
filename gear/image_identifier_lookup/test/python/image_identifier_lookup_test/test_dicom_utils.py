"""Unit tests for DICOM parsing utilities."""

from pathlib import Path

import pytest
from image_identifier_lookup_app.dicom_utils import (
    InvalidDicomError,
    read_dicom_tag,
)
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ImplicitVRLittleEndian


def create_test_dicom_file(
    tmp_path: Path, filename: str = "test.dcm"
) -> tuple[Path, Dataset]:
    """Helper function to create a valid DICOM file for testing.

    Args:
        tmp_path: Temporary directory path from pytest fixture
        filename: Name of the DICOM file to create

    Returns:
        Tuple of (file_path, dataset) for the created DICOM file
    """
    # Create file meta information
    file_meta = FileMetaDataset()
    # Use setattr to bypass mypy type checking for pydicom UID types
    setattr(file_meta, "MediaStorageSOPClassUID", "1.2.840.10008.5.1.4.1.1.2")  # noqa: B010
    setattr(file_meta, "MediaStorageSOPInstanceUID", "1.2.3.4.5.6.7.8.9")  # noqa: B010
    setattr(file_meta, "TransferSyntaxUID", ImplicitVRLittleEndian)  # noqa: B010

    # Create dataset
    ds = Dataset()
    ds.file_meta = file_meta
    setattr(ds, "SOPClassUID", file_meta.MediaStorageSOPClassUID)  # noqa: B010
    setattr(ds, "SOPInstanceUID", file_meta.MediaStorageSOPInstanceUID)  # noqa: B010

    # Save to file
    dicom_file = tmp_path / filename
    ds.save_as(str(dicom_file), write_like_original=False)

    return dicom_file, ds


class TestReadDicomTag:
    """Tests for read_dicom_tag function."""

    def test_read_valid_patient_id_tag(self, tmp_path: Path) -> None:
        """Test reading PatientID tag from valid DICOM file."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add PatientID to the dataset and save again
        ds.PatientID = "110001"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read the PatientID tag
        result = read_dicom_tag(dicom_file, (0x0010, 0x0020))

        assert result == "110001"

    def test_read_valid_study_date_tag(self, tmp_path: Path) -> None:
        """Test reading StudyDate tag from valid DICOM file."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add StudyDate to the dataset and save again
        ds.StudyDate = "20240115"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read the StudyDate tag
        result = read_dicom_tag(dicom_file, (0x0008, 0x0020))

        assert result == "20240115"

    def test_read_valid_modality_tag(self, tmp_path: Path) -> None:
        """Test reading Modality tag from valid DICOM file."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add Modality to the dataset and save again
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read the Modality tag
        result = read_dicom_tag(dicom_file, (0x0008, 0x0060))

        assert result == "MR"

    def test_read_missing_optional_tag_returns_none(self, tmp_path: Path) -> None:
        """Test that missing optional tags return None."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add PatientID but not SeriesDescription
        ds.PatientID = "110001"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Try to read SeriesDescription tag (not present)
        result = read_dicom_tag(dicom_file, (0x0008, 0x103E))

        assert result is None

    def test_read_tag_with_empty_value_returns_empty_string(
        self, tmp_path: Path
    ) -> None:
        """Test that tags with empty value return empty string.

        Note: pydicom saves None values as empty strings, so we test
        that behavior here.
        """
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add PatientID with empty value
        ds.PatientID = ""
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read the PatientID tag
        result = read_dicom_tag(dicom_file, (0x0010, 0x0020))

        # Empty string is returned for empty tags
        assert result == ""

    def test_read_nonexistent_file_raises_invalid_dicom_error(
        self,
    ) -> None:
        """Test that reading a nonexistent file raises InvalidDicomError."""
        nonexistent_file = Path("/nonexistent/file.dcm")

        with pytest.raises(InvalidDicomError) as exc_info:
            read_dicom_tag(nonexistent_file, (0x0010, 0x0020))

        assert "DICOM file not found" in str(exc_info.value)
        assert str(nonexistent_file) in str(exc_info.value)

    def test_read_invalid_dicom_file_raises_error(self, tmp_path: Path) -> None:
        """Test that reading an invalid DICOM file raises InvalidDicomError."""
        # Create a non-DICOM file
        invalid_file = tmp_path / "not_dicom.txt"
        invalid_file.write_text("This is not a DICOM file")

        with pytest.raises(InvalidDicomError) as exc_info:
            read_dicom_tag(invalid_file, (0x0010, 0x0020))

        assert "Invalid DICOM file" in str(exc_info.value)
        assert str(invalid_file) in str(exc_info.value)

    def test_read_corrupted_dicom_file_raises_error(self, tmp_path: Path) -> None:
        """Test that reading a corrupted DICOM file raises
        InvalidDicomError."""
        # Create a file that starts like DICOM but is corrupted
        corrupted_file = tmp_path / "corrupted.dcm"
        corrupted_file.write_bytes(b"DICM" + b"\x00" * 100)

        with pytest.raises(InvalidDicomError) as exc_info:
            read_dicom_tag(corrupted_file, (0x0010, 0x0020))

        # The error message will be "Invalid DICOM file" for corrupted files
        assert "Invalid DICOM file" in str(exc_info.value)
        assert str(corrupted_file) in str(exc_info.value)

    def test_read_all_identifier_fields(self, tmp_path: Path) -> None:
        """Test extraction of all identifier fields."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add all identifier fields
        ds.PatientID = "110001"
        ds.StudyInstanceUID = "1.2.840.113619.2.1.1.1"
        ds.SeriesInstanceUID = "1.2.840.113619.2.1.1.2"
        ds.SeriesNumber = "5"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read all identifier tags
        patient_id = read_dicom_tag(dicom_file, (0x0010, 0x0020))
        study_uid = read_dicom_tag(dicom_file, (0x0020, 0x000D))
        series_uid = read_dicom_tag(dicom_file, (0x0020, 0x000E))
        series_num = read_dicom_tag(dicom_file, (0x0020, 0x0011))

        assert patient_id == "110001"
        assert study_uid == "1.2.840.113619.2.1.1.1"
        assert series_uid == "1.2.840.113619.2.1.1.2"
        assert series_num == "5"

    def test_read_all_descriptive_fields(self, tmp_path: Path) -> None:
        """Test extraction of all descriptive fields."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add all descriptive fields
        ds.Modality = "MR"
        ds.MagneticFieldStrength = "3.0"
        ds.Manufacturer = "Siemens"
        ds.ManufacturerModelName = "Prisma"
        ds.SeriesDescription = "T1 MPRAGE"
        ds.ImagesInAcquisition = "192"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read all descriptive tags
        modality = read_dicom_tag(dicom_file, (0x0008, 0x0060))
        field_strength = read_dicom_tag(dicom_file, (0x0018, 0x0087))
        manufacturer = read_dicom_tag(dicom_file, (0x0008, 0x0070))
        model = read_dicom_tag(dicom_file, (0x0008, 0x1090))
        description = read_dicom_tag(dicom_file, (0x0008, 0x103E))
        images = read_dicom_tag(dicom_file, (0x0020, 0x1002))

        assert modality == "MR"
        assert field_strength == "3.0"
        assert manufacturer == "Siemens"
        assert model == "Prisma"
        assert description == "T1 MPRAGE"
        assert images == "192"

    def test_read_missing_descriptive_fields_returns_none(self, tmp_path: Path) -> None:
        """Test that missing optional descriptive fields return None."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add minimal required fields
        ds.PatientID = "110001"
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Try to read optional descriptive tags
        field_strength = read_dicom_tag(dicom_file, (0x0018, 0x0087))
        manufacturer = read_dicom_tag(dicom_file, (0x0008, 0x0070))
        model = read_dicom_tag(dicom_file, (0x0008, 0x1090))
        description = read_dicom_tag(dicom_file, (0x0008, 0x103E))
        images = read_dicom_tag(dicom_file, (0x0020, 0x1002))

        assert field_strength is None
        assert manufacturer is None
        assert model is None
        assert description is None
        assert images is None

    def test_read_numeric_tag_value_converted_to_string(self, tmp_path: Path) -> None:
        """Test that numeric tag values are converted to strings."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add numeric values
        ds.SeriesNumber = 5  # Integer value
        ds.MagneticFieldStrength = 3.0  # Float value
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read numeric tags
        series_num = read_dicom_tag(dicom_file, (0x0020, 0x0011))
        field_strength = read_dicom_tag(dicom_file, (0x0018, 0x0087))

        assert series_num == "5"
        assert field_strength == "3.0"

    def test_read_date_fields(self, tmp_path: Path) -> None:
        """Test extraction of date fields."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add date fields
        ds.StudyDate = "20240115"
        ds.SeriesDate = "20240115"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read date tags
        study_date = read_dicom_tag(dicom_file, (0x0008, 0x0020))
        series_date = read_dicom_tag(dicom_file, (0x0008, 0x0021))

        assert study_date == "20240115"
        assert series_date == "20240115"

    def test_read_missing_series_date_returns_none(self, tmp_path: Path) -> None:
        """Test that missing SeriesDate (optional) returns None."""
        dicom_file, ds = create_test_dicom_file(tmp_path)

        # Add StudyDate but not SeriesDate
        ds.StudyDate = "20240115"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Read SeriesDate tag (not present)
        series_date = read_dicom_tag(dicom_file, (0x0008, 0x0021))

        assert series_date is None


class TestInvalidDicomError:
    """Tests for InvalidDicomError exception."""

    def test_invalid_dicom_error_is_exception(self) -> None:
        """Test that InvalidDicomError is an Exception."""
        error = InvalidDicomError("Test error")
        assert isinstance(error, Exception)

    def test_invalid_dicom_error_message(self) -> None:
        """Test that InvalidDicomError preserves error message."""
        message = "Failed to parse DICOM file"
        error = InvalidDicomError(message)
        assert str(error) == message

    def test_invalid_dicom_error_with_cause(self) -> None:
        """Test that InvalidDicomError can wrap another exception."""
        original_error = ValueError("Original error")
        error = InvalidDicomError("Wrapped error")
        error.__cause__ = original_error

        assert error.__cause__ is original_error
        assert str(error) == "Wrapped error"
