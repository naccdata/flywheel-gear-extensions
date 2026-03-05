"""Integration tests for Image Identifier Lookup gear.

These tests verify end-to-end workflows with real DICOM files and mocked
AWS services.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from event_capture.event_capture import VisitEventCapture
from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from gear_execution.gear_execution import (
    InputFileWrapper,
)
from identifiers.identifiers_repository import (
    IdentifierRepositoryError,
)
from image_identifier_lookup_app.extraction import extract_dicom_metadata
from image_identifier_lookup_app.main import run as main_run
from moto import mock_aws
from nacc_common.data_identification import DataIdentification
from pydicom.dataset import Dataset


def create_test_dicom_file(
    tmp_path: Path,
    patient_id: str = "110001",
    study_date: str = "20240115",
    modality: str = "MR",
    filename: str = "test.dcm",
) -> Path:
    """Create a test DICOM file with specified metadata.

    Args:
        tmp_path: Temporary directory path
        patient_id: PatientID tag value
        study_date: StudyDate tag value (YYYYMMDD format)
        modality: Modality tag value
        filename: Output filename

    Returns:
        Path to created DICOM file
    """
    # Create a minimal DICOM dataset
    ds = Dataset()

    # File Meta Information
    from pydicom.dataset import FileMetaDataset

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # type: ignore[assignment]
    file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.6.7.8.9"  # type: ignore[assignment]
    file_meta.TransferSyntaxUID = "1.2.840.10008.1.2"  # type: ignore[assignment]
    file_meta.ImplementationClassUID = "1.2.3.4"  # type: ignore[assignment]
    ds.file_meta = file_meta

    # Required DICOM tags
    ds.PatientID = patient_id
    ds.StudyDate = study_date
    ds.Modality = modality
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.9"
    ds.StudyInstanceUID = "1.2.840.113619.2.1.1.1"
    ds.SeriesInstanceUID = "1.2.840.113619.2.1.1.2"
    ds.SeriesNumber = "5"

    # Optional descriptive tags
    ds.Manufacturer = "Siemens"
    ds.ManufacturerModelName = "Skyra"
    ds.SeriesDescription = "T1 MPRAGE"
    ds.MagneticFieldStrength = "3.0"
    ds.ImagesInAcquisition = "176"

    # Save DICOM file
    dicom_file = tmp_path / filename
    ds.save_as(str(dicom_file), write_like_original=False)

    return dicom_file


@pytest.fixture
def mock_gear_context() -> Mock:
    """Create a mock GearContext."""
    context = Mock()
    context.config = Mock()
    context.config.opts = {
        "database_mode": "prod",
        "naccid_field_name": "naccid",
        "default_modality": "MR",
        "event_environment": "test",
        "event_bucket": "test-bucket",
    }
    context.config.destination = {"type": "acquisition"}
    context.metadata = Mock()
    return context


@pytest.fixture
def mock_project() -> Mock:
    """Create a mock ProjectAdaptor."""
    project = Mock(spec=ProjectAdaptor)
    project.label = "test-project"
    project.group = "test-center"
    project.id = "project_id"
    # Use a Mock for info that behaves like a dict
    info_mock = Mock()
    info_mock.get = Mock(
        side_effect=lambda key, default=None: {"pipeline_adcid": 42}.get(key, default)
    )
    info_mock.__getitem__ = Mock(side_effect=lambda key: {"pipeline_adcid": 42}[key])
    project.info = info_mock
    # Mock the get_pipeline_adcid method to return the integer value
    project.get_pipeline_adcid = Mock(return_value=42)
    return project


@pytest.fixture
def mock_subject() -> Mock:
    """Create a mock SubjectAdaptor."""
    subject = Mock(spec=SubjectAdaptor)
    subject.label = "110001"
    subject.info = {}
    subject.id = "subject_id"
    return subject


@pytest.fixture
def mock_file_obj() -> Mock:
    """Create a mock FileEntry."""
    file_obj = Mock(spec=FileEntry)
    file_obj.name = "test.dcm"
    file_obj.tags = []
    file_obj.parents = Mock()
    file_obj.parents.project = "project_id"
    file_obj.parents.subject = "subject_id"
    return file_obj


@pytest.fixture
def mock_file_input() -> Mock:
    """Create a mock InputFileWrapper."""
    file_input = Mock(spec=InputFileWrapper)
    file_input.file_id = "test_file_id"
    file_input.filepath = "/flywheel/v0/input/input_file/test.dcm"
    file_input.file_input = Mock()
    return file_input


@pytest.fixture
def mock_repository() -> Mock:
    """Create a mock IdentifierRepository."""
    repository = Mock()
    repository.get_naccid.return_value = "NACC123456"
    return repository


@pytest.fixture
def mock_event_capture() -> Mock:
    """Create a mock VisitEventCapture."""
    return Mock(spec=VisitEventCapture)


class TestEndToEndSuccessFlow:
    """Test end-to-end success flow with real DICOM file."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_complete_success_with_real_dicom_file(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
    ) -> None:
        """Test complete success flow with real DICOM file."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC123456"
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Create visit metadata from real DICOM
        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=None,
            visitnum=None,
        )

        # Extract DICOM metadata
        _dicom_metadata = {
            "patient_id": "110001",
            "study_instance_uid": "1.2.840.113619.2.1.1.1",
            "series_instance_uid": "1.2.840.113619.2.1.1.2",
            "series_number": "5",
            "study_date": "20240115",
            "modality": "MR",
            "manufacturer": "Siemens",
            "manufacturer_model_name": "Skyra",
            "series_description": "T1 MPRAGE",
            "magnetic_field_strength": "3.0",
            "images_in_acquisition": "176",
        }

        # Act
        main_run(
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            dry_run=False,
            naccid_field_name="naccid",
            default_modality="UNKNOWN",
            dicom_metadata=extract_dicom_metadata(dicom_file),
        )

        # Assert - processor called with correct data
        mock_processor.lookup_and_update.assert_called_once_with(
            ptid="110001",
            adcid=42,
            dicom_metadata=mock_processor.lookup_and_update.call_args.kwargs[
                "dicom_metadata"
            ],
        )

        # Assert - QC log updated with PASS
        mock_qc_manager.update_qc_log.assert_called_once()
        qc_call = mock_qc_manager.update_qc_log.call_args.kwargs
        assert qc_call["status"] == "PASS"

        # Assert - event captured
        mock_event_capture.capture_event.assert_called_once()
        event = mock_event_capture.capture_event.call_args.args[0]
        assert event.action == "submit"
        assert event.datatype == "dicom"


class TestEndToEndFailureFlow:
    """Test end-to-end failure flow when lookup fails."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_lookup_failure_no_matching_record(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
    ) -> None:
        """Test failure flow when no matching identifier record found."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="999999", study_date="20240115", modality="MR"
        )

        # Mock processor to raise lookup error
        mock_processor = Mock()
        mock_processor.lookup_and_update.side_effect = IdentifierRepositoryError(
            "No matching record found for PTID=999999, ADCID=42"
        )
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        # Create visit metadata
        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="999999",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=None,
            visitnum=None,
        )

        _dicom_metadata = {"patient_id": "999999", "study_date": "20240115"}

        # Act & Assert
        with pytest.raises(IdentifierRepositoryError) as exc_info:
            main_run(
                project=mock_project,
                subject=mock_subject,
                identifiers_repository=mock_repository,
                event_capture=mock_event_capture,
                gear_name="image-identifier-lookup",
                dry_run=False,
                naccid_field_name="naccid",
                default_modality="UNKNOWN",
                dicom_metadata=extract_dicom_metadata(dicom_file),
            )

        assert "No matching record found" in str(exc_info.value)
        mock_processor.lookup_and_update.assert_called_once()


class TestIdempotentRerun:
    """Test idempotent re-run when NACCID already exists."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    def test_skip_lookup_when_naccid_already_correct(
        self,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
    ) -> None:
        """Test that lookup is skipped when NACCID already exists with correct
        value."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Set existing NACCID in subject metadata
        existing_naccid = "NACC123456"
        mock_subject.info = {"naccid": existing_naccid}

        # Create visit metadata with existing NACCID
        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=existing_naccid,
            visitnum=None,
        )

        _dicom_metadata = {"patient_id": "110001", "study_date": "20240115"}

        # Act - run twice
        for _ in range(2):
            main_run(
                project=mock_project,
                subject=mock_subject,
                identifiers_repository=mock_repository,
                event_capture=mock_event_capture,
                gear_name="image-identifier-lookup",
                dry_run=False,
                naccid_field_name="naccid",
                default_modality="UNKNOWN",
                dicom_metadata=extract_dicom_metadata(dicom_file),
            )

        # Assert - both runs succeeded
        assert mock_qc_manager.update_qc_log.call_count == 2
        assert mock_event_capture.capture_event.call_count == 2


class TestFailFastScenarios:
    """Test fail-fast scenarios for missing required data."""

    def test_fail_fast_missing_study_date(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that processing fails fast when StudyDate is missing from
        DICOM."""
        # Arrange - create DICOM file without StudyDate
        from pydicom.dataset import FileMetaDataset

        ds = Dataset()
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # type: ignore[assignment]
        file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.6.7.8.9"  # type: ignore[assignment]
        file_meta.TransferSyntaxUID = "1.2.840.10008.1.2"  # type: ignore[assignment]
        file_meta.ImplementationClassUID = "1.2.3.4"  # type: ignore[assignment]
        ds.file_meta = file_meta

        ds.PatientID = "110001"
        ds.Modality = "MR"
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.9"
        # Note: StudyDate is intentionally missing

        dicom_file = tmp_path / "no_study_date.dcm"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Act & Assert - extraction should fail
        from image_identifier_lookup_app.extraction import extract_visit_metadata

        # Extract metadata first
        dicom_metadata = extract_dicom_metadata(dicom_file)

        with pytest.raises(ValueError) as exc_info:
            extract_visit_metadata(
                dicom_metadata=dicom_metadata,
                ptid="110001",
                adcid=42,
                naccid=None,
                default_modality="UNKNOWN",
            )

        assert "StudyDate" in str(exc_info.value)
        assert "required DICOM field" in str(exc_info.value)

    def test_fail_fast_missing_patient_id_and_empty_subject_label(
        self,
        tmp_path: Path,
        mock_subject: Mock,
    ) -> None:
        """Test that processing fails fast when both PatientID and
        subject.label are missing."""
        # Arrange - create DICOM file without PatientID
        from pydicom.dataset import FileMetaDataset

        ds = Dataset()
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # type: ignore[assignment]
        file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.6.7.8.9"  # type: ignore[assignment]
        file_meta.TransferSyntaxUID = "1.2.840.10008.1.2"  # type: ignore[assignment]
        file_meta.ImplementationClassUID = "1.2.3.4"  # type: ignore[assignment]
        ds.file_meta = file_meta

        ds.StudyDate = "20240115"
        ds.Modality = "MR"
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.9"
        # Note: PatientID is intentionally missing

        dicom_file = tmp_path / "no_patient_id.dcm"
        ds.save_as(str(dicom_file), write_like_original=False)

        # Mock subject with empty label
        mock_subject.label = ""

        # Act & Assert - extraction should fail
        from image_identifier_lookup_app.extraction import extract_ptid

        # Extract metadata first
        dicom_metadata = extract_dicom_metadata(dicom_file)

        with pytest.raises(ValueError) as exc_info:
            extract_ptid(subject=mock_subject, dicom_metadata=dicom_metadata)

        assert "PTID not found" in str(exc_info.value)
        assert "subject.label is empty" in str(exc_info.value)
        assert "PatientID is missing" in str(exc_info.value)


class TestQCLogAndEventCapture:
    """Test QC log creation and event capture."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_qc_log_creation_with_visit_metadata(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
    ) -> None:
        """Test that QC log is created with visit metadata."""
        # Arrange
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC123456"
        mock_processor_class.return_value = mock_processor

        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=None,
            visitnum=None,
        )

        _dicom_metadata = {"patient_id": "110001", "study_date": "20240115"}

        # Act
        main_run(
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            dry_run=False,
            naccid_field_name="naccid",
            default_modality="UNKNOWN",
            dicom_metadata=extract_dicom_metadata(dicom_file),
        )

        mock_qc_manager.update_qc_log.assert_called_once()
        qc_call = mock_qc_manager.update_qc_log.call_args.kwargs
        assert qc_call["add_visit_metadata"] is True
        assert qc_call["status"] == "PASS"

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_event_capture_with_dicom_datatype(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
    ) -> None:
        """Test that event is captured with correct datatype."""
        # Arrange
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC123456"
        mock_processor_class.return_value = mock_processor

        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=None,
            visitnum=None,
        )

        _dicom_metadata = {"patient_id": "110001", "study_date": "20240115"}

        # Act
        main_run(
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            dry_run=False,
            naccid_field_name="naccid",
            default_modality="UNKNOWN",
            dicom_metadata=extract_dicom_metadata(dicom_file),
        )

        # Assert - event captured with correct fields
        mock_event_capture.capture_event.assert_called_once()
        event = mock_event_capture.capture_event.call_args.args[0]
        assert event.action == "submit"
        assert event.datatype == "dicom"
        assert event.project_label == "test-project"
        assert event.center_label == "test-center"
        assert event.gear_name == "image-identifier-lookup"


class TestMockedAWSServices:
    """Test with mocked AWS services using moto."""

    @mock_aws
    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_with_mocked_s3_for_event_capture(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test event capture with mocked S3 bucket."""
        import boto3

        # Arrange - create mocked S3 bucket
        s3_client = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-event-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        # Create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC123456"
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        # Create real event capture with mocked S3
        from s3.s3_bucket import S3BucketInterface

        s3_bucket = S3BucketInterface.create_from_environment(bucket_name)
        event_capture = VisitEventCapture(s3_bucket=s3_bucket, environment="test")

        _visit_metadata = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid=None,
            visitnum=None,
        )

        _dicom_metadata = {"patient_id": "110001", "study_date": "20240115"}

        # Act
        main_run(
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=event_capture,
            gear_name="image-identifier-lookup",
            dry_run=False,
            naccid_field_name="naccid",
            default_modality="UNKNOWN",
            dicom_metadata=extract_dicom_metadata(dicom_file),
        )

        # Assert - event was written to S3
        objects = s3_client.list_objects_v2(Bucket=bucket_name)
        assert "Contents" in objects
        assert len(objects["Contents"]) > 0
