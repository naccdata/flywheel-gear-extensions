"""Tests for FileVisitAnnotator."""

from unittest.mock import Mock

from error_logging.qc_status_log_creator import FileVisitAnnotator
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import VisitKeys


class TestFileVisitAnnotator:
    """Tests for FileVisitAnnotator."""

    def test_annotate_qc_log_file_success(self):
        """Test successful QC log file annotation."""
        # Create test visit keys
        visit_keys = VisitKeys(
            ptid="TEST001",
            date="2024-01-15",
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Mock project and file
        mock_project = Mock(spec=ProjectAdaptor)
        mock_file = Mock()
        mock_file.update_info = Mock()
        mock_project.get_file.return_value = mock_file

        # Create annotator
        annotator = FileVisitAnnotator(mock_project)

        # Annotate QC log file
        success = annotator.annotate_qc_log_file(
            qc_log_filename="TEST001_2024-01-15_uds_qc-status.log",
            visit_keys=visit_keys,
        )

        # Verify success
        assert success, "Annotation should succeed"

        # Verify file was retrieved
        mock_project.get_file.assert_called_once_with(
            "TEST001_2024-01-15_uds_qc-status.log"
        )

        # Verify file info was updated
        mock_file.update_info.assert_called_once()
        call_args = mock_file.update_info.call_args[0][0]

        assert "visit" in call_args, "Should contain visit metadata"
        visit_metadata = call_args["visit"]

        assert visit_metadata["ptid"] == "TEST001"
        assert visit_metadata["date"] == "2024-01-15"
        assert visit_metadata["module"] == "UDS"
        assert visit_metadata["visitnum"] == "1"
        assert visit_metadata["adcid"] == 42

    def test_annotate_qc_log_file_insufficient_data(self):
        """Test annotation with insufficient visit data."""
        # Create visit keys with missing data
        visit_keys = VisitKeys(
            ptid="TEST001",
            date=None,  # Missing date
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Mock project
        mock_project = Mock(spec=ProjectAdaptor)

        # Create annotator
        annotator = FileVisitAnnotator(mock_project)

        # Annotate QC log file
        success = annotator.annotate_qc_log_file(
            qc_log_filename="test_qc-status.log", visit_keys=visit_keys
        )

        # Should fail due to missing date
        assert not success, "Annotation should fail with insufficient data"

        # File should not be retrieved since validation fails early
        mock_project.get_file.assert_not_called()

    def test_annotate_qc_log_file_not_found(self):
        """Test annotation when QC log file is not found."""
        # Create test visit keys
        visit_keys = VisitKeys(
            ptid="TEST001",
            date="2024-01-15",
            module="UDS",
            visitnum="1",
            adcid=42,
        )

        # Mock project to return None (file not found)
        mock_project = Mock(spec=ProjectAdaptor)
        mock_project.get_file.return_value = None

        # Create annotator
        annotator = FileVisitAnnotator(mock_project)

        # Annotate QC log file
        success = annotator.annotate_qc_log_file(
            qc_log_filename="nonexistent_qc-status.log", visit_keys=visit_keys
        )

        # Should fail due to file not found
        assert not success, "Annotation should fail when file not found"

        # File retrieval should have been attempted
        mock_project.get_file.assert_called_once_with("nonexistent_qc-status.log")

    def test_create_visit_metadata_filters_none_values(self):
        """Test that visit metadata creation filters out None values."""
        # Create visit keys with some None values
        visit_keys = VisitKeys(
            ptid="TEST001",
            date="2024-01-15",
            module="UDS",
            visitnum=None,  # None value
            adcid=None,  # None value
        )

        # Mock project and file for successful annotation
        mock_project = Mock(spec=ProjectAdaptor)
        mock_file = Mock()
        mock_file.update_info = Mock()
        mock_project.get_file.return_value = mock_file

        # Create annotator
        annotator = FileVisitAnnotator(mock_project)

        # Annotate file to trigger metadata creation
        success = annotator.annotate_qc_log_file("test.log", visit_keys)
        assert success

        # Get the metadata from the call
        call_args = mock_file.update_info.call_args[0][0]
        metadata = call_args["visit"]

        # Verify None values are filtered out
        assert "ptid" in metadata
        assert "date" in metadata
        assert "module" in metadata
        assert "visitnum" not in metadata  # Should be filtered out
        assert "adcid" not in metadata  # Should be filtered out

        # Verify values are correct
        assert metadata["ptid"] == "TEST001"
        assert metadata["date"] == "2024-01-15"
        assert metadata["module"] == "UDS"
