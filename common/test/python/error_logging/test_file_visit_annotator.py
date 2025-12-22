"""Unit tests for FileVisitAnnotator changes to use VisitMetadata."""

from unittest.mock import Mock, patch

from error_logging.qc_status_log_creator import FileVisitAnnotator
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import VisitMetadata


class TestFileVisitAnnotatorVisitMetadata:
    """Test FileVisitAnnotator with VisitMetadata including packet field."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_project = Mock(spec=ProjectAdaptor)
        self.annotator = FileVisitAnnotator(self.mock_project)

    def test_annotate_qc_log_file_with_packet_field(self):
        """Test annotation with VisitMetadata including packet field."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110001",
            date="2024-01-15",
            module="UDS",
            visitnum="01",
            packet="I",
            adcid=123,
        )
        qc_log_filename = "test-qc-log.json"

        mock_file = Mock()
        self.mock_project.get_file.return_value = mock_file

        with patch(
            "error_logging.qc_status_log_creator.update_file_info"
        ) as mock_update:
            # Act
            result = self.annotator.annotate_qc_log_file(
                qc_log_filename, visit_metadata
            )

            # Assert
            assert result is True
            self.mock_project.get_file.assert_called_once_with(qc_log_filename)

            # Verify that update_file_info was called with visit metadata
            # including packet
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[1]["file"] == mock_file

            # Check that the custom_info contains visit metadata with packet
            custom_info = call_args[1]["custom_info"]
            assert "visit" in custom_info
            visit_data = custom_info["visit"]
            assert visit_data["ptid"] == "110001"
            assert visit_data["date"] == "2024-01-15"
            assert visit_data["module"] == "UDS"
            assert visit_data["visitnum"] == "01"
            assert visit_data["packet"] == "I"
            assert visit_data["adcid"] == 123

    def test_annotate_qc_log_file_without_packet_field(self):
        """Test annotation with VisitMetadata without packet field (None)."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110002",
            date="2024-01-16",
            module="FTD",
            visitnum="02",
            packet=None,  # Explicitly None
            adcid=124,
        )
        qc_log_filename = "test-qc-log-2.json"

        mock_file = Mock()
        self.mock_project.get_file.return_value = mock_file

        with patch(
            "error_logging.qc_status_log_creator.update_file_info"
        ) as mock_update:
            # Act
            result = self.annotator.annotate_qc_log_file(
                qc_log_filename, visit_metadata
            )

            # Assert
            assert result is True

            # Check that the custom_info contains visit metadata without packet
            # (excluded by exclude_none=True)
            custom_info = mock_update.call_args[1]["custom_info"]
            visit_data = custom_info["visit"]
            assert visit_data["ptid"] == "110002"
            assert visit_data["date"] == "2024-01-16"
            assert visit_data["module"] == "FTD"
            assert visit_data["visitnum"] == "02"
            assert (
                "packet" not in visit_data
            )  # Should be excluded due to exclude_none=True
            assert visit_data["adcid"] == 124

    def test_annotate_qc_log_file_missing_required_fields(self):
        """Test annotation fails gracefully with missing required fields."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid=None,  # Missing required field
            date="2024-01-15",
            module="UDS",
            visitnum="01",
            packet="I",
        )
        qc_log_filename = "test-qc-log.json"

        # Act
        result = self.annotator.annotate_qc_log_file(qc_log_filename, visit_metadata)

        # Assert
        assert result is False
        self.mock_project.get_file.assert_not_called()

    def test_annotate_qc_log_file_missing_file(self):
        """Test annotation fails gracefully when QC log file is not found."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110001", date="2024-01-15", module="UDS", visitnum="01", packet="I"
        )
        qc_log_filename = "missing-qc-log.json"

        self.mock_project.get_file.return_value = None

        # Act
        result = self.annotator.annotate_qc_log_file(qc_log_filename, visit_metadata)

        # Assert
        assert result is False
        self.mock_project.get_file.assert_called_once_with(qc_log_filename)

    def test_annotate_qc_log_file_update_file_info_exception(self):
        """Test annotation handles update_file_info exceptions gracefully."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110001", date="2024-01-15", module="UDS", visitnum="01", packet="I"
        )
        qc_log_filename = "test-qc-log.json"

        mock_file = Mock()
        self.mock_project.get_file.return_value = mock_file

        with patch(
            "error_logging.qc_status_log_creator.update_file_info"
        ) as mock_update:
            mock_update.side_effect = Exception("S3 error")

            # Act
            result = self.annotator.annotate_qc_log_file(
                qc_log_filename, visit_metadata
            )

            # Assert
            assert result is False

    def test_create_visit_metadata_uses_model_dump(self):
        """Test that _create_visit_metadata uses
        VisitMetadata.model_dump(mode='raw')."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110001",
            date="2024-01-15",
            module="UDS",
            visitnum="01",
            packet="I",
            adcid=123,
            naccid="NACC001",
        )

        # Act
        result = self.annotator._create_visit_metadata(visit_metadata)  # noqa: SLF001

        # Assert
        assert isinstance(result, dict)
        assert result["ptid"] == "110001"
        assert result["date"] == "2024-01-15"  # Raw field name, not transformed
        assert result["module"] == "UDS"
        assert result["visitnum"] == "01"  # Raw field name, not transformed
        assert result["packet"] == "I"
        assert result["adcid"] == 123
        assert result["naccid"] == "NACC001"

    def test_backward_compatibility_with_existing_qc_status_logs(self):
        """Test that the annotation doesn't break existing QC status log
        structure."""
        # Arrange
        visit_metadata = VisitMetadata(
            ptid="110001", date="2024-01-15", module="UDS", visitnum="01", packet="I"
        )
        qc_log_filename = "existing-qc-log.json"

        mock_file = Mock()
        # Simulate existing file with some QC data
        mock_file.info = {
            "qc": {"some-gear": {"validation": {"state": "PASS", "data": []}}}
        }
        self.mock_project.get_file.return_value = mock_file

        with patch(
            "error_logging.qc_status_log_creator.update_file_info"
        ) as mock_update:
            # Act
            result = self.annotator.annotate_qc_log_file(
                qc_log_filename, visit_metadata
            )

            # Assert
            assert result is True

            # Verify that only visit metadata is added, existing structure preserved
            custom_info = mock_update.call_args[1]["custom_info"]
            assert "visit" in custom_info
            assert len(custom_info) == 1  # Only visit metadata added

            # The existing qc data should remain untouched
            # (update_file_info handles this)
            visit_data = custom_info["visit"]
            assert visit_data["ptid"] == "110001"
            assert visit_data["packet"] == "I"
