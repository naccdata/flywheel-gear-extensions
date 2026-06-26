"""Unit tests for ImageIdentifierLookupProcessor."""

from typing import Any
from unittest.mock import Mock

import pytest
from flywheel.rest import ApiException
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject
from image_identifier_lookup_app.processor import ImageIdentifierLookupProcessor


@pytest.fixture
def mock_repository() -> Mock:
    """Create a mock IdentifierRepository."""
    return Mock(spec=IdentifierRepository)


@pytest.fixture
def mock_subject() -> Mock:
    """Create a mock SubjectAdaptor."""
    return Mock(spec=SubjectAdaptor)


@pytest.fixture
def sample_dicom_metadata() -> dict[str, Any]:
    """Create sample DICOM metadata for testing."""
    return {
        "patient_id": "110001",
        "study_instance_uid": "1.2.840.113619.2.1.1.1",
        "series_instance_uid": "1.2.840.113619.2.1.1.2",
        "series_number": "5",
        "study_date": "20240115",
        "series_date": "20240115",
        "modality": "MR",
        "magnetic_field_strength": "3.0",
        "manufacturer": "Siemens",
        "manufacturer_model_name": "Prisma",
        "series_description": "T1 MPRAGE",
        "images_in_acquisition": "192",
    }


@pytest.fixture
def processor(
    mock_repository: Mock, mock_subject: Mock
) -> ImageIdentifierLookupProcessor:
    """Create an ImageIdentifierLookupProcessor instance for testing."""
    return ImageIdentifierLookupProcessor(
        identifiers_repository=mock_repository,
        subject=mock_subject,
        naccid_field_name="naccid",
    )


class TestImageIdentifierLookupProcessor:
    """Tests for ImageIdentifierLookupProcessor class."""

    def test_successful_naccid_lookup_and_metadata_update(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test successful NACCID lookup and metadata update."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        result_naccid = processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert
        assert result_naccid == expected_naccid
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)
        mock_subject.update.assert_called_once_with(
            info={"naccid": expected_naccid, "dicom_metadata": sample_dicom_metadata}
        )

    def test_dry_run_skips_metadata_update(
        self,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test that dry_run mode performs lookup but skips metadata update.

        Note: This tests the processor level. Integration tests verify that
        dry_run also skips QC logging and event capture at the main.run() level.
        """
        # Arrange
        processor = ImageIdentifierLookupProcessor(
            identifiers_repository=mock_repository,
            subject=mock_subject,
            naccid_field_name="naccid",
            dry_run=True,
        )

        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        result_naccid = processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert
        assert result_naccid == expected_naccid
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)
        # Verify metadata update was NOT called in dry run mode
        mock_subject.update.assert_not_called()

    def test_lookup_failure_no_matching_record(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test lookup failure when no matching record is found."""
        # Arrange
        ptid = "999999"
        adcid = 42

        # Mock lookup returning None (no matching record)
        mock_repository.get.return_value = None

        # Act & Assert
        with pytest.raises(IdentifierRepositoryError) as exc_info:
            processor.lookup_and_update(
                ptid=ptid,
                adcid=adcid,
                dicom_metadata=sample_dicom_metadata,
            )

        assert "No matching identifier record found" in str(exc_info.value)
        assert f"PTID={ptid}" in str(exc_info.value)
        assert f"ADCID={adcid}" in str(exc_info.value)
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)
        mock_subject.update.assert_not_called()

    def test_lookup_failure_repository_unavailable(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test lookup failure when repository is unavailable."""
        # Arrange
        ptid = "110001"
        adcid = 42

        # Mock repository raising an error
        mock_repository.get.side_effect = IdentifierRepositoryError(
            "Service unavailable"
        )

        # Act & Assert
        with pytest.raises(IdentifierRepositoryError) as exc_info:
            processor.lookup_and_update(
                ptid=ptid,
                adcid=adcid,
                dicom_metadata=sample_dicom_metadata,
            )

        assert "Service unavailable" in str(exc_info.value)
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)
        mock_subject.update.assert_not_called()

    def test_metadata_update_with_naccid_and_dicom_metadata(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test metadata update includes both NACCID and DICOM metadata."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert - verify update was called with both NACCID and DICOM metadata
        mock_subject.update.assert_called_once()
        call_args = mock_subject.update.call_args
        assert call_args.kwargs["info"]["naccid"] == expected_naccid
        assert call_args.kwargs["info"]["dicom_metadata"] == sample_dicom_metadata

    def test_metadata_update_failure_handling(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test metadata update failure handling."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Mock subject update failure
        mock_subject.update.side_effect = ApiException(reason="Internal Server Error")

        # Act & Assert
        with pytest.raises(ApiException) as exc_info:
            processor.lookup_and_update(
                ptid=ptid,
                adcid=adcid,
                dicom_metadata=sample_dicom_metadata,
            )

        assert "Internal Server Error" in str(exc_info.value)
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)
        mock_subject.update.assert_called_once()

    def test_custom_naccid_field_name(
        self,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test that custom NACCID field name is used in metadata update."""
        # Arrange
        custom_field_name = "custom_naccid_field"
        processor = ImageIdentifierLookupProcessor(
            identifiers_repository=mock_repository,
            subject=mock_subject,
            naccid_field_name=custom_field_name,
        )

        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert - verify custom field name is used
        mock_subject.update.assert_called_once()
        call_args = mock_subject.update.call_args
        assert custom_field_name in call_args.kwargs["info"]
        assert call_args.kwargs["info"][custom_field_name] == expected_naccid

    def test_minimal_dicom_metadata(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test metadata update with minimal DICOM metadata."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Minimal DICOM metadata with only required fields
        minimal_metadata = {
            "patient_id": "110001",
            "study_date": "20240115",
            "modality": "MR",
        }

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=minimal_metadata,
        )

        # Assert
        mock_subject.update.assert_called_once()
        call_args = mock_subject.update.call_args
        assert call_args.kwargs["info"]["dicom_metadata"] == minimal_metadata

    def test_empty_dicom_metadata(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
    ) -> None:
        """Test metadata update with empty DICOM metadata dictionary."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Empty DICOM metadata
        empty_metadata: dict[str, Any] = {}

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=empty_metadata,
        )

        # Assert
        mock_subject.update.assert_called_once()
        call_args = mock_subject.update.call_args
        assert call_args.kwargs["info"]["dicom_metadata"] == empty_metadata

    def test_lookup_with_special_characters_in_ptid(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test lookup with special characters in PTID."""
        # Arrange
        ptid = "ABC_123"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        result_naccid = processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert
        assert result_naccid == expected_naccid
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)

    def test_repository_get_called_with_correct_parameters(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test that repository.get is called with correct parameters."""
        # Arrange
        ptid = "110001"
        adcid = 99
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert - verify exact parameters passed to repository.get
        mock_repository.get.assert_called_once_with(adcid=adcid, ptid=ptid)

    def test_subject_update_called_with_correct_structure(
        self,
        processor: ImageIdentifierLookupProcessor,
        mock_repository: Mock,
        mock_subject: Mock,
        sample_dicom_metadata: dict[str, Any],
    ) -> None:
        """Test that subject.update is called with correct structure."""
        # Arrange
        ptid = "110001"
        adcid = 42
        expected_naccid = "NACC123456"

        # Mock successful lookup
        identifier = IdentifierObject(
            adcid=adcid,
            ptid=ptid,
            naccid=expected_naccid,
            guid="test_guid",
            naccadc=1,
            active=True,
        )
        mock_repository.get.return_value = identifier

        # Act
        processor.lookup_and_update(
            ptid=ptid,
            adcid=adcid,
            dicom_metadata=sample_dicom_metadata,
        )

        # Assert - verify exact structure of update call
        mock_subject.update.assert_called_once()
        call_args = mock_subject.update.call_args
        assert "info" in call_args.kwargs
        info_dict = call_args.kwargs["info"]
        assert "naccid" in info_dict
        assert "dicom_metadata" in info_dict
        assert len(info_dict) == 2  # Only these two keys
