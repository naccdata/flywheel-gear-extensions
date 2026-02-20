"""Unit tests for data extraction utilities."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from image_identifier_lookup_app.dicom_utils import InvalidDicomError
from image_identifier_lookup_app.extraction import (
    extract_dicom_metadata,
    extract_existing_naccid,
    extract_pipeline_adcid,
    extract_ptid,
    extract_visit_metadata,
    format_dicom_date,
)
from nacc_common.data_identification import DataIdentification
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


class TestExtractPipelineAdcid:
    """Tests for extract_pipeline_adcid function."""

    def test_extract_valid_adcid(self) -> None:
        """Test extracting valid pipeline ADCID from project metadata."""
        # Create mock project with valid ADCID
        project = Mock(spec=ProjectAdaptor)
        project.label = "test-project"
        project.get_pipeline_adcid.return_value = 42

        result = extract_pipeline_adcid(project)

        assert result == 42
        project.get_pipeline_adcid.assert_called_once()

    def test_extract_adcid_raises_project_error_when_missing(self) -> None:
        """Test that missing ADCID raises ProjectError."""
        # Create mock project that raises ProjectError
        project = Mock(spec=ProjectAdaptor)
        project.label = "test-project"
        project.get_pipeline_adcid.side_effect = ProjectError(
            "Project test-group/test-project has no ADCID"
        )

        with pytest.raises(ProjectError) as exc_info:
            extract_pipeline_adcid(project)

        assert "has no ADCID" in str(exc_info.value)

    def test_extract_adcid_raises_project_error_on_api_failure(self) -> None:
        """Test that API failures raise ProjectError."""
        # Create mock project that raises ProjectError
        project = Mock(spec=ProjectAdaptor)
        project.label = "test-project"
        project.get_pipeline_adcid.side_effect = ProjectError("API error")

        with pytest.raises(ProjectError) as exc_info:
            extract_pipeline_adcid(project)

        assert "API error" in str(exc_info.value)


class TestExtractPtid:
    """Tests for extract_ptid function."""

    def test_extract_ptid_from_subject_label(self, tmp_path: Path) -> None:
        """Test extracting PTID from subject.label (primary path)."""
        # Create mock subject with label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = "110001"

        # Create dummy DICOM file (won't be read)
        dicom_file, _ = create_test_dicom_file(tmp_path)

        result = extract_ptid(subject, dicom_file)

        assert result == "110001"

    def test_extract_ptid_strips_whitespace_from_subject_label(
        self, tmp_path: Path
    ) -> None:
        """Test that whitespace is stripped from subject.label."""
        # Create mock subject with label containing whitespace
        subject = Mock(spec=SubjectAdaptor)
        subject.label = "  110001  "

        # Create dummy DICOM file (won't be read)
        dicom_file, _ = create_test_dicom_file(tmp_path)

        result = extract_ptid(subject, dicom_file)

        assert result == "110001"

    def test_extract_ptid_from_dicom_fallback(self, tmp_path: Path) -> None:
        """Test extracting PTID from DICOM PatientID tag (fallback)."""
        # Create mock subject with empty label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = ""

        # Create DICOM file with PatientID
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.PatientID = "110002"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_ptid(subject, dicom_file)

        assert result == "110002"

    def test_extract_ptid_strips_whitespace_from_dicom(self, tmp_path: Path) -> None:
        """Test that whitespace is stripped from DICOM PatientID."""
        # Create mock subject with empty label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = ""

        # Create DICOM file with PatientID containing whitespace
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.PatientID = "  110002  "
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_ptid(subject, dicom_file)

        assert result == "110002"

    def test_extract_ptid_prefers_subject_label_over_dicom(
        self, tmp_path: Path
    ) -> None:
        """Test that subject.label is preferred over DICOM PatientID."""
        # Create mock subject with label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = "110001"

        # Create DICOM file with different PatientID
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.PatientID = "110002"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_ptid(subject, dicom_file)

        # Should use subject.label, not DICOM PatientID
        assert result == "110001"

    def test_extract_ptid_fails_when_both_sources_empty(self, tmp_path: Path) -> None:
        """Test that extraction fails when both subject.label and DICOM
        PatientID are empty."""
        # Create mock subject with empty label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = ""

        # Create DICOM file without PatientID
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.save_as(str(dicom_file), write_like_original=False)

        with pytest.raises(ValueError) as exc_info:
            extract_ptid(subject, dicom_file)

        assert "PTID not found" in str(exc_info.value)
        assert "subject.label is empty" in str(exc_info.value)
        assert "DICOM PatientID tag is missing" in str(exc_info.value)

    def test_extract_ptid_fails_when_subject_label_none(self, tmp_path: Path) -> None:
        """Test that extraction fails when subject.label is None."""
        # Create mock subject with None label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = None

        # Create DICOM file without PatientID
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.save_as(str(dicom_file), write_like_original=False)

        with pytest.raises(ValueError) as exc_info:
            extract_ptid(subject, dicom_file)

        assert "PTID not found" in str(exc_info.value)

    def test_extract_ptid_raises_invalid_dicom_error_for_bad_file(
        self, tmp_path: Path
    ) -> None:
        """Test that invalid DICOM file raises InvalidDicomError."""
        # Create mock subject with empty label
        subject = Mock(spec=SubjectAdaptor)
        subject.label = ""

        # Create non-DICOM file
        invalid_file = tmp_path / "not_dicom.txt"
        invalid_file.write_text("This is not a DICOM file")

        with pytest.raises(InvalidDicomError):
            extract_ptid(subject, invalid_file)


class TestExtractExistingNaccid:
    """Tests for extract_existing_naccid function."""

    def test_extract_existing_naccid_present(self) -> None:
        """Test extracting existing NACCID from subject.info."""
        # Create mock subject with NACCID in info
        subject = Mock(spec=SubjectAdaptor)
        subject.info = {"naccid": "NACC123456"}

        result = extract_existing_naccid(subject, "naccid")

        assert result == "NACC123456"

    def test_extract_existing_naccid_absent(self) -> None:
        """Test that missing NACCID returns None."""
        # Create mock subject without NACCID in info
        subject = Mock(spec=SubjectAdaptor)
        subject.info = {"other_field": "value"}

        result = extract_existing_naccid(subject, "naccid")

        assert result is None

    def test_extract_existing_naccid_empty_info(self) -> None:
        """Test that empty subject.info returns None."""
        # Create mock subject with empty info
        subject = Mock(spec=SubjectAdaptor)
        subject.info = {}

        result = extract_existing_naccid(subject, "naccid")

        assert result is None

    def test_extract_existing_naccid_custom_field_name(self) -> None:
        """Test extracting NACCID with custom field name."""
        # Create mock subject with custom field name
        subject = Mock(spec=SubjectAdaptor)
        subject.info = {"custom_naccid": "NACC789012"}

        result = extract_existing_naccid(subject, "custom_naccid")

        assert result == "NACC789012"


class TestExtractVisitMetadata:
    """Tests for extract_visit_metadata function."""

    def test_extract_visit_metadata_with_valid_dicom_data(self, tmp_path: Path) -> None:
        """Test extracting visit metadata from valid DICOM file."""
        # Create DICOM file with required fields
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.StudyDate = "20240115"
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_visit_metadata(
            file_path=dicom_file,
            ptid="110001",
            adcid=42,
            naccid="NACC123456",
            default_modality="UNKNOWN",
        )

        assert isinstance(result, DataIdentification)
        assert result.participant.ptid == "110001"
        assert result.participant.adcid == 42
        assert result.participant.naccid == "NACC123456"
        assert result.date == "2024-01-15"
        # Type narrowing: we know data is ImageIdentification
        from nacc_common.data_identification import ImageIdentification

        assert isinstance(result.data, ImageIdentification)
        assert result.data.modality == "MR"
        assert result.visit is None

    def test_extract_visit_metadata_with_missing_modality_uses_default(
        self, tmp_path: Path
    ) -> None:
        """Test that missing modality uses default value."""
        # Create DICOM file without Modality tag
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.StudyDate = "20240115"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_visit_metadata(
            file_path=dicom_file,
            ptid="110001",
            adcid=42,
            naccid="NACC123456",
            default_modality="CT",
        )

        # Type narrowing: we know data is ImageIdentification
        from nacc_common.data_identification import ImageIdentification

        assert isinstance(result.data, ImageIdentification)
        assert result.data.modality == "CT"

    def test_extract_visit_metadata_fails_when_study_date_missing(
        self, tmp_path: Path
    ) -> None:
        """Test that missing StudyDate raises ValueError."""
        # Create DICOM file without StudyDate
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        with pytest.raises(ValueError) as exc_info:
            extract_visit_metadata(
                file_path=dicom_file,
                ptid="110001",
                adcid=42,
                naccid="NACC123456",
                default_modality="UNKNOWN",
            )

        assert "Visit date not found" in str(exc_info.value)
        assert "StudyDate (0008,0020) is missing" in str(exc_info.value)
        assert "required DICOM field" in str(exc_info.value)

    def test_extract_visit_metadata_with_none_naccid(self, tmp_path: Path) -> None:
        """Test extracting visit metadata with None NACCID."""
        # Create DICOM file with required fields
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.StudyDate = "20240115"
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_visit_metadata(
            file_path=dicom_file,
            ptid="110001",
            adcid=42,
            naccid=None,
            default_modality="UNKNOWN",
        )

        assert result.participant.naccid is None

    def test_extract_visit_metadata_raises_invalid_dicom_error_for_bad_file(
        self, tmp_path: Path
    ) -> None:
        """Test that invalid DICOM file raises InvalidDicomError."""
        # Create non-DICOM file
        invalid_file = tmp_path / "not_dicom.txt"
        invalid_file.write_text("This is not a DICOM file")

        with pytest.raises(InvalidDicomError):
            extract_visit_metadata(
                file_path=invalid_file,
                ptid="110001",
                adcid=42,
                naccid="NACC123456",
                default_modality="UNKNOWN",
            )


class TestExtractDicomMetadata:
    """Tests for extract_dicom_metadata function."""

    def test_extract_dicom_metadata_with_all_fields_present(
        self, tmp_path: Path
    ) -> None:
        """Test extracting all DICOM metadata fields when present."""
        # Create DICOM file with all fields
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.PatientID = "110001"
        ds.StudyInstanceUID = "1.2.840.113619.2.1.1.1"
        ds.SeriesInstanceUID = "1.2.840.113619.2.1.1.2"
        ds.SeriesNumber = "5"
        ds.StudyDate = "20240115"
        ds.SeriesDate = "20240115"
        ds.Modality = "MR"
        ds.MagneticFieldStrength = "3.0"
        ds.Manufacturer = "Siemens"
        ds.ManufacturerModelName = "Prisma"
        ds.SeriesDescription = "T1 MPRAGE"
        ds.ImagesInAcquisition = "192"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_dicom_metadata(dicom_file)

        # Verify all identifier fields
        assert result["patient_id"] == "110001"
        assert result["study_instance_uid"] == "1.2.840.113619.2.1.1.1"
        assert result["series_instance_uid"] == "1.2.840.113619.2.1.1.2"
        assert result["series_number"] == "5"

        # Verify date fields
        assert result["study_date"] == "20240115"
        assert result["series_date"] == "20240115"

        # Verify descriptive fields
        assert result["modality"] == "MR"
        assert result["magnetic_field_strength"] == "3.0"
        assert result["manufacturer"] == "Siemens"
        assert result["manufacturer_model_name"] == "Prisma"
        assert result["series_description"] == "T1 MPRAGE"
        assert result["images_in_acquisition"] == "192"

    def test_extract_dicom_metadata_with_missing_optional_fields(
        self, tmp_path: Path
    ) -> None:
        """Test that missing optional fields return None."""
        # Create DICOM file with minimal fields
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.PatientID = "110001"
        ds.StudyDate = "20240115"
        ds.Modality = "MR"
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_dicom_metadata(dicom_file)

        # Required fields should be present
        assert result["patient_id"] == "110001"
        assert result["study_date"] == "20240115"
        assert result["modality"] == "MR"

        # Optional fields should be None
        assert result["study_instance_uid"] is None
        assert result["series_instance_uid"] is None
        assert result["series_number"] is None
        assert result["series_date"] is None
        assert result["magnetic_field_strength"] is None
        assert result["manufacturer"] is None
        assert result["manufacturer_model_name"] is None
        assert result["series_description"] is None
        assert result["images_in_acquisition"] is None

    def test_extract_dicom_metadata_returns_dict_with_all_keys(
        self, tmp_path: Path
    ) -> None:
        """Test that result dictionary contains all expected keys."""
        # Create minimal DICOM file
        dicom_file, ds = create_test_dicom_file(tmp_path)
        ds.save_as(str(dicom_file), write_like_original=False)

        result = extract_dicom_metadata(dicom_file)

        # Verify all expected keys are present
        expected_keys = {
            "patient_id",
            "study_instance_uid",
            "series_instance_uid",
            "series_number",
            "study_date",
            "series_date",
            "modality",
            "magnetic_field_strength",
            "manufacturer",
            "manufacturer_model_name",
            "series_description",
            "images_in_acquisition",
        }

        assert set(result.keys()) == expected_keys

    def test_extract_dicom_metadata_raises_invalid_dicom_error_for_bad_file(
        self, tmp_path: Path
    ) -> None:
        """Test that invalid DICOM file raises InvalidDicomError."""
        # Create non-DICOM file
        invalid_file = tmp_path / "not_dicom.txt"
        invalid_file.write_text("This is not a DICOM file")

        with pytest.raises(InvalidDicomError):
            extract_dicom_metadata(invalid_file)


class TestFormatDicomDate:
    """Tests for format_dicom_date function."""

    def test_format_valid_dicom_date(self) -> None:
        """Test formatting valid DICOM date (YYYYMMDD) to ISO format (YYYY-MM-
        DD)."""
        result = format_dicom_date("20240115")
        assert result == "2024-01-15"

    def test_format_dicom_date_with_different_dates(self) -> None:
        """Test formatting various valid DICOM dates."""
        assert format_dicom_date("20231231") == "2023-12-31"
        assert format_dicom_date("20240101") == "2024-01-01"
        assert format_dicom_date("19990615") == "1999-06-15"

    def test_format_dicom_date_with_invalid_length_raises_error(self) -> None:
        """Test that date with invalid length raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            format_dicom_date("2024011")  # 7 characters

        assert "Invalid DICOM date format" in str(exc_info.value)
        assert "2024011" in str(exc_info.value)

    def test_format_dicom_date_with_too_long_string_raises_error(self) -> None:
        """Test that date with too many characters raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            format_dicom_date("202401155")  # 9 characters

        assert "Invalid DICOM date format" in str(exc_info.value)

    def test_format_dicom_date_with_empty_string_raises_error(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            format_dicom_date("")

        assert "Invalid DICOM date format" in str(exc_info.value)

    def test_format_dicom_date_with_non_numeric_characters(self) -> None:
        """Test that date with non-numeric characters is formatted (no
        validation)."""
        # Note: format_dicom_date only validates length, not content
        # It will format any 8-character string
        result = format_dicom_date("20XX0115")
        assert result == "20XX-01-15"


class TestProjectError:
    """Tests for ProjectError exception."""

    def test_project_error_is_exception(self) -> None:
        """Test that ProjectError is an Exception."""
        error = ProjectError("Test error")
        assert isinstance(error, Exception)

    def test_project_error_message(self) -> None:
        """Test that ProjectError preserves error message."""
        message = "Failed to extract ADCID"
        error = ProjectError(message)
        assert str(error) == message

    def test_project_error_with_cause(self) -> None:
        """Test that ProjectError can wrap another exception."""
        original_error = ValueError("Original error")
        error = ProjectError("Wrapped error")
        error.__cause__ = original_error

        assert error.__cause__ is original_error
        assert str(error) == "Wrapped error"
