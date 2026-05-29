"""Unit tests for ImageIdentifierLookupVisitor and main orchestration."""

from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import pytest
from botocore.exceptions import ClientError
from event_capture.event_capture import VisitEventCapture
from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelError, ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from image_identifier_lookup_app.extraction import (
    LookupContext,
    extract_dicom_metadata,
)
from image_identifier_lookup_app.main import ImageIdentifierLookup
from image_identifier_lookup_app.run import ImageIdentifierLookupVisitor
from nacc_common.data_identification import DataIdentification
from outputs.error_writer import ListErrorWriter
from s3.s3_bucket import S3InterfaceError


def _build_lookup_context(
    *,
    pipeline_adcid: int = 42,
    ptid: str = "110001",
    existing_naccid: str | None = None,
    dicom_metadata: dict | None = None,
) -> LookupContext:
    """Build a LookupContext with optional DICOM enrichment.

    When dicom_metadata is provided, calls enrich_from_dicom() to
    populate visit_metadata — matching what run.py does in production.
    """
    ctx = LookupContext(
        pipeline_adcid=pipeline_adcid,
        ptid=ptid,
        existing_naccid=existing_naccid,
    )
    if dicom_metadata is not None:
        ctx.enrich_from_dicom(dicom_metadata)
    return ctx


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
    from pydicom.dataset import Dataset, FileMetaDataset

    # Create a minimal DICOM dataset
    ds = Dataset()

    # File Meta Information
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
        "event_environment": "test",
        "event_bucket": "test-bucket",
    }
    context.config.destination = {"type": "acquisition"}
    context.metadata = Mock()
    return context


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock ClientWrapper."""
    return Mock(spec=ClientWrapper)


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
    return Mock(spec=IdentifierRepository)


@pytest.fixture
def mock_event_capture() -> Mock:
    """Create a mock VisitEventCapture."""
    return Mock(spec=VisitEventCapture)


@pytest.fixture
def mock_project() -> Mock:
    """Create a mock ProjectAdaptor."""
    project = Mock(spec=ProjectAdaptor)
    project.label = "test-project"
    project.group = "test-center"
    project.id = "project_id"
    # Use a real dict (not Mock) for info to avoid Pydantic validation errors
    project.info = {"pipeline_adcid": 42}
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
def error_writer() -> ListErrorWriter:
    """Create a ListErrorWriter for testing."""
    return ListErrorWriter(container_id="test_file_id", fw_path="test/path")


@pytest.fixture
def visitor(
    mock_client: Mock,
    mock_file_input: Mock,
    mock_repository: Mock,
    mock_event_capture: Mock,
) -> ImageIdentifierLookupVisitor:
    """Create an ImageIdentifierLookupVisitor instance."""
    return ImageIdentifierLookupVisitor(
        client=mock_client,
        file_input=mock_file_input,
        identifiers_repository=mock_repository,
        event_capture=mock_event_capture,
        gear_name="image-identifier-lookup",
        naccid_field_name="naccid",
    )


class TestImageIdentifierLookupVisitorCreate:
    """Tests for ImageIdentifierLookupVisitor.create() factory method."""

    @patch("image_identifier_lookup_app.run.GearBotClient.create")
    @patch("image_identifier_lookup_app.run.InputFileWrapper.create")
    @patch("image_identifier_lookup_app.run.S3BucketInterface.create_from_environment")
    @patch("image_identifier_lookup_app.run.create_lambda_client")
    def test_create_with_valid_configuration(
        self,
        mock_lambda_client: Mock,
        mock_s3_bucket: Mock,
        mock_input_wrapper: Mock,
        mock_gear_bot: Mock,
    ) -> None:
        """Test visitor creation with valid configuration."""
        # Arrange
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "database_mode": "prod",
            "naccid_field_name": "naccid",
            "event_environment": "test",
            "event_bucket": "test-bucket",
        }
        context.manifest = Mock()
        context.manifest.name = "image-identifier-lookup"
        parameter_store = Mock()

        mock_gear_bot.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)
        mock_s3_bucket.return_value = Mock()

        # Act
        visitor = ImageIdentifierLookupVisitor.create(context, parameter_store)

        # Assert
        assert visitor is not None
        mock_gear_bot.assert_called_once_with(
            context=context, parameter_store=parameter_store
        )
        mock_input_wrapper.assert_called_once_with(
            input_name="input_file", context=context
        )
        mock_s3_bucket.assert_called_once_with("test-bucket")

    @patch("image_identifier_lookup_app.run.GearBotClient.create")
    @patch("image_identifier_lookup_app.run.InputFileWrapper.create")
    def test_create_fails_without_event_environment(
        self, mock_input_wrapper: Mock, mock_gear_bot: Mock
    ) -> None:
        """Test visitor creation fails when event_environment is missing."""
        # Arrange
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "database_mode": "prod",
            "event_bucket": "test-bucket",
        }
        parameter_store = Mock()

        mock_gear_bot.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        # Act & Assert
        with pytest.raises(GearExecutionError) as exc_info:
            ImageIdentifierLookupVisitor.create(context, parameter_store)

        assert "event_environment and event_bucket are required" in str(exc_info.value)

    @patch("image_identifier_lookup_app.run.GearBotClient.create")
    @patch("image_identifier_lookup_app.run.InputFileWrapper.create")
    def test_create_fails_without_event_bucket(
        self, mock_input_wrapper: Mock, mock_gear_bot: Mock
    ) -> None:
        """Test visitor creation fails when event_bucket is missing."""
        # Arrange
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "database_mode": "prod",
            "event_environment": "test",
        }
        parameter_store = Mock()

        mock_gear_bot.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)

        # Act & Assert
        with pytest.raises(GearExecutionError) as exc_info:
            ImageIdentifierLookupVisitor.create(context, parameter_store)

        assert "event_environment and event_bucket are required" in str(exc_info.value)

    @patch("image_identifier_lookup_app.run.GearBotClient.create")
    @patch("image_identifier_lookup_app.run.InputFileWrapper.create")
    @patch("image_identifier_lookup_app.run.S3BucketInterface.create_from_environment")
    def test_create_fails_when_s3_bucket_inaccessible(
        self,
        mock_s3_bucket: Mock,
        mock_input_wrapper: Mock,
        mock_gear_bot: Mock,
    ) -> None:
        """Test visitor creation fails when S3 bucket is inaccessible."""
        # Arrange
        context = Mock()
        context.config = Mock()
        context.config.opts = {
            "database_mode": "prod",
            "event_environment": "test",
            "event_bucket": "test-bucket",
        }
        parameter_store = Mock()

        mock_gear_bot.return_value = Mock(spec=ClientWrapper)
        mock_input_wrapper.return_value = Mock(spec=InputFileWrapper)
        mock_s3_bucket.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket"}}, "HeadBucket"
        )

        # Act & Assert
        with pytest.raises(GearExecutionError) as exc_info:
            ImageIdentifierLookupVisitor.create(context, parameter_store)

        assert "Failed to initialize event capture" in str(exc_info.value)
        assert "Unable to access S3 bucket" in str(exc_info.value)


class TestMainOrchestration:
    """Tests for main.run() orchestration function."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_successful_end_to_end_flow(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test successful end-to-end flow: extraction → lookup → update → QC →
        event."""
        # Arrange - create a real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Extract DICOM metadata
        dicom_metadata = extract_dicom_metadata(dicom_file)

        # Act
        success, data_identification = ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=dicom_metadata,
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - processor called
        mock_processor.lookup_and_update.assert_called_once()
        call_kwargs = mock_processor.lookup_and_update.call_args.kwargs
        assert call_kwargs["ptid"] == "110001"
        assert call_kwargs["adcid"] == 42

        # Assert - QC log updated
        assert mock_qc_manager.update_qc_log.called

        # Assert - event captured
        assert mock_event_capture.capture_event.called

        # Assert - success
        assert success is True
        assert not error_writer.errors()

        # Assert - DataIdentification returned
        assert data_identification is not None
        assert isinstance(data_identification, DataIdentification)
        assert data_identification.ptid == "110001"
        assert data_identification.adcid == 42
        assert data_identification.modality == "MR"
        assert data_identification.date == "2024-01-15"

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_idempotency_skip_when_naccid_already_correct(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test idempotency: skip lookup when NACCID already correct."""
        # Arrange - create a real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        existing_naccid = "NACC123456"
        mock_subject.info = {"naccid": existing_naccid}

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act
        success, data_identification = ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=existing_naccid,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - processor NOT created (skipped)
        mock_processor_class.assert_not_called()

        # Assert - QC log still updated
        assert mock_qc_manager.update_qc_log.called

        # Assert - event still captured
        assert mock_event_capture.capture_event.called

        # Assert - success
        assert success is True

        # Assert - DataIdentification returned with existing NACCID
        assert data_identification is not None
        assert isinstance(data_identification, DataIdentification)
        assert data_identification.naccid == existing_naccid

    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    def test_qc_logging_on_success(
        self,
        mock_qc_manager_class: Mock,
        mock_processor_class: Mock,
        tmp_path: Path,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        error_writer: ListErrorWriter,
    ) -> None:
        """Test QC logging on successful processing."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act
        ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - QC log updated with PASS status
        mock_qc_manager.update_qc_log.assert_called_once()
        call_kwargs = mock_qc_manager.update_qc_log.call_args.kwargs
        assert call_kwargs["status"] == "PASS"
        assert call_kwargs["gear_name"] == "image-identifier-lookup"
        assert call_kwargs["add_visit_metadata"] is True

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_qc_logging_on_failure(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test QC logging on processing failure."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        # Mock processor to raise error
        mock_processor = Mock()
        mock_processor.lookup_and_update.side_effect = IdentifierRepositoryError(
            "No matching record"
        )
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act - error is now captured, not raised
        success, data_identification = ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - failure captured in errors
        assert success is False
        assert error_writer.has_errors()

        # Assert - QC log updated with FAIL status
        mock_qc_manager.update_qc_log.assert_called_once()
        qc_call = mock_qc_manager.update_qc_log.call_args.kwargs
        assert qc_call["status"] == "FAIL"

        # Assert - DataIdentification still returned even on failure
        assert data_identification is not None
        assert isinstance(data_identification, DataIdentification)

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_event_capture_on_success(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test event capture on successful processing."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act
        ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - event captured
        mock_event_capture.capture_event.assert_called_once()
        captured_event = mock_event_capture.capture_event.call_args.args[0]
        assert captured_event.action == "submit"
        assert captured_event.datatype == "dicom"
        assert captured_event.project_label == "test-project"
        assert captured_event.center_label == "test-center"

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_event_capture_failure_is_non_critical(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that event capture failure doesn't fail the gear."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager_class.return_value = mock_qc_manager

        # Mock event capture to fail with S3InterfaceError
        mock_event_capture.capture_event.side_effect = S3InterfaceError("S3 error")

        # Act - should not raise exception
        ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - event capture was attempted but failure didn't stop processing
        mock_event_capture.capture_event.assert_called_once()


class TestRunDataIdentificationReturn:
    """Tests for the DataIdentification third element of run() return value."""

    def test_run_returns_none_data_identification_without_visit_metadata(
        self,
        mock_project: Mock,
        mock_subject: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that run() returns None as third element when visit metadata is
        unavailable (no DICOM enrichment, so no study_date/modality)."""
        # Arrange - build context WITHOUT dicom_metadata so visit_metadata is None
        lookup_context = _build_lookup_context(
            pipeline_adcid=42,
            ptid="110001",
            existing_naccid="NACC123456",
            dicom_metadata=None,
        )
        assert lookup_context.visit_metadata is None

        # Act
        success, data_identification = ImageIdentifierLookup(
            lookup_context=lookup_context,
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert
        assert success is True
        assert data_identification is None

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_run_returns_data_identification_matching_lookup_context(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_project: Mock,
        mock_subject: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that the returned DataIdentification matches the one built from
        the lookup context."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="CT"
        )

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC999999"
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = "qc-status.log"
        mock_qc_manager_class.return_value = mock_qc_manager

        lookup_context = _build_lookup_context(
            pipeline_adcid=99,
            ptid="220002",
            existing_naccid=None,
            dicom_metadata=extract_dicom_metadata(dicom_file),
        )

        # Act
        success, data_identification = ImageIdentifierLookup(
            lookup_context=lookup_context,
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - DataIdentification matches the lookup context
        assert data_identification is not None
        assert isinstance(data_identification, DataIdentification)
        assert data_identification.ptid == lookup_context.ptid
        assert data_identification.adcid == lookup_context.pipeline_adcid
        assert data_identification.modality == "CT"
        assert data_identification.date == "2024-01-15"
        assert data_identification.visitnum is None

    def test_run_returns_2_tuple(
        self,
        mock_project: Mock,
        mock_subject: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that run() always returns a 2-tuple."""
        # Arrange - context without visit metadata
        lookup_context = _build_lookup_context(
            pipeline_adcid=42,
            ptid="110001",
            existing_naccid="NACC123456",
            dicom_metadata=None,
        )

        # Act
        result = ImageIdentifierLookup(
            lookup_context=lookup_context,
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - always a 2-tuple
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestVisitorRun:
    """Tests for ImageIdentifierLookupVisitor.run() method."""

    @patch("image_identifier_lookup_app.run.resolve_dicom_file")
    @patch("image_identifier_lookup_app.run.extract_dicom_metadata")
    @patch("image_identifier_lookup_app.run.ImageIdentifierLookup")
    def test_visitor_run_calls_main_with_correct_parameters(
        self,
        mock_lookup_class: Mock,
        mock_extract_metadata: Mock,
        mock_resolve_dicom: Mock,
        visitor: ImageIdentifierLookupVisitor,
        mock_gear_context: Mock,
        mock_project: Mock,
        mock_subject: Mock,
        mock_file_obj: Mock,
    ) -> None:
        """Test that visitor.run() calls main with correct parameters."""
        # Arrange - mock the proxy property
        mock_proxy = Mock()
        mock_proxy.get_file.return_value = mock_file_obj
        mock_fw_project = Mock()
        mock_proxy.get_project_by_id.return_value = mock_fw_project
        mock_project.get_subject_by_id.return_value = mock_subject

        # Mock resolve_dicom_file to return the path unchanged
        mock_resolve_dicom.return_value = (
            Path("/flywheel/v0/input/input_file/test.dcm"),
            None,
        )

        # Mock extract_dicom_metadata to return test metadata
        mock_extract_metadata.return_value = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        # Mock ImageIdentifierLookup to return success
        mock_instance = Mock()
        mock_instance.run.return_value = (True, None)
        mock_lookup_class.return_value = mock_instance

        with (
            patch.object(
                type(visitor),
                "proxy",
                new_callable=PropertyMock,
                return_value=mock_proxy,
            ),
            patch(
                "image_identifier_lookup_app.run.ProjectAdaptor",
                return_value=mock_project,
            ),
        ):
            # Act
            visitor.run(mock_gear_context)

            # Assert - extract_dicom_metadata was called
            mock_extract_metadata.assert_called_once()

            # Assert - ImageIdentifierLookup was constructed and run
            mock_lookup_class.assert_called_once()
            call_kwargs = mock_lookup_class.call_args.kwargs
            assert call_kwargs["gear_name"] == "image-identifier-lookup"
            assert "lookup_context" in call_kwargs
            mock_instance.run.assert_called_once()


class TestIntegrationScenarios:
    """Integration-style tests for complete scenarios."""

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_complete_success_scenario_with_all_components(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test complete success scenario with all components working
        together."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        ptid = "110001"
        adcid = 42
        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act
        ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert complete workflow
        # 1. Processor created and lookup performed
        mock_processor_class.assert_called_once()
        mock_processor.lookup_and_update.assert_called_once()
        call_kwargs = mock_processor.lookup_and_update.call_args.kwargs
        assert call_kwargs["ptid"] == ptid
        assert call_kwargs["adcid"] == adcid

        # 2. QC log updated with PASS status
        mock_qc_manager.update_qc_log.assert_called_once()
        qc_call = mock_qc_manager.update_qc_log.call_args.kwargs
        assert qc_call["status"] == "PASS"
        assert qc_call["add_visit_metadata"] is True

        # 3. Event captured
        mock_event_capture.capture_event.assert_called_once()
        event = mock_event_capture.capture_event.call_args.args[0]
        assert event.action == "submit"
        assert event.datatype == "dicom"

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    def test_idempotent_rerun_scenario(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test idempotent re-run scenario where NACCID already exists."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        existing_naccid = "NACC123456"

        # Set existing NACCID in subject
        mock_subject.info = {"naccid": existing_naccid}

        # Mock QC manager
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.return_value = (
            "110001_2024-01-15_mr_qc-status.log"
        )
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act - run twice with same NACCID
        for _ in range(2):
            ImageIdentifierLookup(
                lookup_context=_build_lookup_context(
                    pipeline_adcid=42,
                    ptid="110001",
                    existing_naccid=existing_naccid,
                    dicom_metadata=extract_dicom_metadata(dicom_file),
                ),
                project=mock_project,
                subject=mock_subject,
                identifiers_repository=mock_repository,
                event_capture=mock_event_capture,
                gear_name="image-identifier-lookup",
                error_writer=error_writer,
            ).run()

        # Assert - both runs succeeded
        # QC log updated twice (once per run)
        assert mock_qc_manager.update_qc_log.call_count == 2

        # Event captured twice (once per run)
        assert mock_event_capture.capture_event.call_count == 2

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_qc_logging_failure_does_not_stop_processing(
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
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that QC logging failure doesn't stop processing."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        naccid = "NACC123456"

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = naccid
        mock_processor_class.return_value = mock_processor

        # Mock QC manager to fail with FlywheelError
        mock_qc_manager = Mock()
        mock_qc_manager.update_qc_log.side_effect = FlywheelError("QC log error")
        mock_qc_manager_class.return_value = mock_qc_manager

        # Act - should not raise exception
        ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            error_writer=error_writer,
        ).run()

        # Assert - processing continued despite QC logging failure
        # Event capture still happened
        mock_event_capture.capture_event.assert_called_once()


class TestDataIdentificationFileWrite:
    """Tests for data_identification write to file metadata via visitor.run().

    Validates Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 5.1,
    5.2
    """

    @patch("image_identifier_lookup_app.run.resolve_dicom_file")
    @patch("image_identifier_lookup_app.run.extract_dicom_metadata")
    @patch("image_identifier_lookup_app.run.ImageIdentifierLookup")
    def test_writes_data_identification_to_file_info(
        self,
        mock_lookup_class: Mock,
        mock_extract_metadata: Mock,
        mock_resolve_dicom: Mock,
        visitor: ImageIdentifierLookupVisitor,
        mock_gear_context: Mock,
        mock_file_obj: Mock,
        mock_project: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test that visitor.run() writes data_identification to file.info when
        ImageIdentifierLookup returns a DataIdentification."""
        data_id = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid="NACC123456",
            visitnum=None,
        )

        mock_proxy = Mock()
        mock_proxy.get_file.return_value = mock_file_obj
        mock_fw_project = Mock()
        mock_proxy.get_project_by_id.return_value = mock_fw_project
        mock_project.get_subject_by_id.return_value = mock_subject

        mock_resolve_dicom.return_value = (
            Path("/flywheel/v0/input/input_file/test.dcm"),
            None,
        )
        mock_extract_metadata.return_value = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        mock_instance = Mock()
        mock_instance.run.return_value = (True, data_id)
        mock_lookup_class.return_value = mock_instance

        with (
            patch.object(
                type(visitor),
                "proxy",
                new_callable=PropertyMock,
                return_value=mock_proxy,
            ),
            patch(
                "image_identifier_lookup_app.run.ProjectAdaptor",
                return_value=mock_project,
            ),
        ):
            visitor.run(mock_gear_context)

        # Find the call that wrote data_identification
        update_calls = mock_gear_context.metadata.update_file_metadata.call_args_list
        data_id_calls = [
            c
            for c in update_calls
            if "info" in c.kwargs and "data_identification" in c.kwargs.get("info", {})
        ]
        assert len(data_id_calls) == 1
        written = data_id_calls[0].kwargs["info"]["data_identification"]
        assert written == data_id.model_dump()

    @patch("image_identifier_lookup_app.run.resolve_dicom_file")
    @patch("image_identifier_lookup_app.run.extract_dicom_metadata")
    @patch("image_identifier_lookup_app.run.ImageIdentifierLookup")
    def test_skips_data_identification_write_when_none(
        self,
        mock_lookup_class: Mock,
        mock_extract_metadata: Mock,
        mock_resolve_dicom: Mock,
        visitor: ImageIdentifierLookupVisitor,
        mock_gear_context: Mock,
        mock_file_obj: Mock,
        mock_project: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test that visitor.run() does NOT write data_identification to
        file.info when ImageIdentifierLookup returns None."""
        mock_proxy = Mock()
        mock_proxy.get_file.return_value = mock_file_obj
        mock_fw_project = Mock()
        mock_proxy.get_project_by_id.return_value = mock_fw_project
        mock_project.get_subject_by_id.return_value = mock_subject

        mock_resolve_dicom.return_value = (
            Path("/flywheel/v0/input/input_file/test.dcm"),
            None,
        )
        mock_extract_metadata.return_value = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        mock_instance = Mock()
        mock_instance.run.return_value = (True, None)
        mock_lookup_class.return_value = mock_instance

        with (
            patch.object(
                type(visitor),
                "proxy",
                new_callable=PropertyMock,
                return_value=mock_proxy,
            ),
            patch(
                "image_identifier_lookup_app.run.ProjectAdaptor",
                return_value=mock_project,
            ),
        ):
            visitor.run(mock_gear_context)

        # Verify no call wrote data_identification
        update_calls = mock_gear_context.metadata.update_file_metadata.call_args_list
        data_id_calls = [
            c
            for c in update_calls
            if "info" in c.kwargs and "data_identification" in c.kwargs.get("info", {})
        ]
        assert len(data_id_calls) == 0

    @patch("image_identifier_lookup_app.run.resolve_dicom_file")
    @patch("image_identifier_lookup_app.run.extract_dicom_metadata")
    @patch("image_identifier_lookup_app.run.ImageIdentifierLookup")
    def test_flywheel_error_during_metadata_write_does_not_raise(
        self,
        mock_lookup_class: Mock,
        mock_extract_metadata: Mock,
        mock_resolve_dicom: Mock,
        visitor: ImageIdentifierLookupVisitor,
        mock_gear_context: Mock,
        mock_file_obj: Mock,
        mock_project: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test that a FlywheelError during file metadata write is logged but
        does not raise from visitor.run()."""
        data_id = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid="NACC123456",
            visitnum=None,
        )

        mock_proxy = Mock()
        mock_proxy.get_file.return_value = mock_file_obj
        mock_fw_project = Mock()
        mock_proxy.get_project_by_id.return_value = mock_fw_project
        mock_project.get_subject_by_id.return_value = mock_subject

        mock_resolve_dicom.return_value = (
            Path("/flywheel/v0/input/input_file/test.dcm"),
            None,
        )
        mock_extract_metadata.return_value = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        mock_instance = Mock()
        mock_instance.run.return_value = (True, data_id)
        mock_lookup_class.return_value = mock_instance

        # Make all metadata writes raise FlywheelError
        mock_gear_context.metadata.add_qc_result.side_effect = FlywheelError(
            "metadata write failed"
        )

        with (
            patch.object(
                type(visitor),
                "proxy",
                new_callable=PropertyMock,
                return_value=mock_proxy,
            ),
            patch(
                "image_identifier_lookup_app.run.ProjectAdaptor",
                return_value=mock_project,
            ),
        ):
            # Should NOT raise
            visitor.run(mock_gear_context)


class TestDryRunBehavior:
    """Tests for dry run behavior with data_identification.

    Validates Requirements: 6.1, 6.2
    """

    @patch("image_identifier_lookup_app.run.resolve_dicom_file")
    @patch("image_identifier_lookup_app.run.extract_dicom_metadata")
    @patch("image_identifier_lookup_app.run.ImageIdentifierLookup")
    def test_dry_run_skips_file_metadata_update(
        self,
        mock_lookup_class: Mock,
        mock_extract_metadata: Mock,
        mock_resolve_dicom: Mock,
        mock_client: Mock,
        mock_file_input: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        mock_gear_context: Mock,
        mock_file_obj: Mock,
        mock_project: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test that data_identification is NOT written to file metadata when
        dry_run=True."""
        # Create visitor with dry_run=True
        dry_run_visitor = ImageIdentifierLookupVisitor(
            client=mock_client,
            file_input=mock_file_input,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            dry_run=True,
            naccid_field_name="naccid",
        )

        data_id = DataIdentification.from_visit_metadata(
            ptid="110001",
            date="2024-01-15",
            modality="MR",
            adcid=42,
            naccid="NACC123456",
            visitnum=None,
        )

        # Mock the proxy property and Flywheel lookups
        mock_proxy = Mock()
        mock_proxy.get_file.return_value = mock_file_obj
        mock_fw_project = Mock()
        mock_proxy.get_project_by_id.return_value = mock_fw_project
        mock_project.get_subject_by_id.return_value = mock_subject

        mock_resolve_dicom.return_value = (
            Path("/flywheel/v0/input/input_file/test.dcm"),
            None,
        )
        mock_extract_metadata.return_value = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        # ImageIdentifierLookup.run() returns data_identification
        mock_instance = Mock()
        mock_instance.run.return_value = (True, data_id)
        mock_lookup_class.return_value = mock_instance

        with (
            patch.object(
                type(dry_run_visitor),
                "proxy",
                new_callable=PropertyMock,
                return_value=mock_proxy,
            ),
            patch(
                "image_identifier_lookup_app.run.ProjectAdaptor",
                return_value=mock_project,
            ),
        ):
            dry_run_visitor.run(mock_gear_context)

        # Assert - no metadata writes occurred
        mock_gear_context.metadata.add_qc_result.assert_not_called()
        mock_gear_context.metadata.update_file_metadata.assert_not_called()

    @patch("image_identifier_lookup_app.main.QCStatusLogManager")
    @patch("image_identifier_lookup_app.main.ImageIdentifierLookupProcessor")
    def test_dry_run_still_returns_data_identification(
        self,
        mock_processor_class: Mock,
        mock_qc_manager_class: Mock,
        tmp_path: Path,
        mock_project: Mock,
        mock_subject: Mock,
        mock_repository: Mock,
        mock_event_capture: Mock,
        error_writer: ListErrorWriter,
    ) -> None:
        """Test that ImageIdentifierLookup.run() still returns a non-None
        DataIdentification when dry_run=True and visit metadata is
        available."""
        # Arrange - create real DICOM file
        dicom_file = create_test_dicom_file(
            tmp_path, patient_id="110001", study_date="20240115", modality="MR"
        )

        # Mock processor
        mock_processor = Mock()
        mock_processor.lookup_and_update.return_value = "NACC123456"
        mock_processor_class.return_value = mock_processor

        # Act - run with dry_run=True
        success, data_identification = ImageIdentifierLookup(
            lookup_context=_build_lookup_context(
                pipeline_adcid=42,
                ptid="110001",
                existing_naccid=None,
                dicom_metadata=extract_dicom_metadata(dicom_file),
            ),
            project=mock_project,
            subject=mock_subject,
            identifiers_repository=mock_repository,
            event_capture=mock_event_capture,
            gear_name="image-identifier-lookup",
            dry_run=True,
            error_writer=error_writer,
        ).run()

        # Assert - DataIdentification is still returned
        assert data_identification is not None
        assert isinstance(data_identification, DataIdentification)
        assert data_identification.ptid == "110001"
        assert data_identification.adcid == 42
        assert data_identification.modality == "MR"
        assert data_identification.date == "2024-01-15"

        # Assert - success
        assert success is True
