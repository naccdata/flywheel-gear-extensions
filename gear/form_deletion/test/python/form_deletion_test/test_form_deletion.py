"""Unit tests for form_deletion_app.main."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from deletions.models import DeletedItems, DeleteRequest
from flywheel.rest import ApiException
from form_deletion_app.main import run, update_file_metadata
from nacc_common.error_models import FileErrorList
from test_mocks.mock_flywheel import MockFile


class TestUpdateFileMetadata:
    def test_success_status_is_pass(self):
        """success=True writes state=PASS to file metadata."""
        mock_file = MockFile(name="delete-request.json")
        deleted = DeletedItems()
        errors = FileErrorList([])

        with patch("form_deletion_app.main.update_file_info") as mock_update:
            update_file_metadata(
                input_file=mock_file,
                success=True,
                deleted_items=deleted,
                errors=errors,
            )

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["custom_info"]["delete_response"]["state"] == "PASS"

    def test_failure_status_is_fail(self):
        """success=False writes state=FAIL to file metadata."""
        mock_file = MockFile(name="delete-request.json")
        deleted = DeletedItems()
        errors = FileErrorList([])

        with patch("form_deletion_app.main.update_file_info") as mock_update:
            update_file_metadata(
                input_file=mock_file,
                success=False,
                deleted_items=deleted,
                errors=errors,
            )

        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["custom_info"]["delete_response"]["state"] == "FAIL"

    def test_api_exception_is_swallowed(self):
        """ApiException from update_file_info is caught; no exception
        propagates."""
        mock_file = MockFile(name="delete-request.json")
        deleted = DeletedItems()
        errors = FileErrorList([])

        with patch(
            "form_deletion_app.main.update_file_info",
            side_effect=ApiException(status=500, reason="server error"),
        ):
            # Should not raise
            update_file_metadata(
                input_file=mock_file,
                success=True,
                deleted_items=deleted,
                errors=errors,
            )

    def test_deleted_items_included_in_metadata(self):
        """Deleted items are serialised into the metadata."""
        mock_file = MockFile(name="delete-request.json")
        deleted = DeletedItems(
            logs=["log1.json"], acquisitions=["group/project/file.json"]
        )
        errors = FileErrorList([])

        with patch("form_deletion_app.main.update_file_info") as mock_update:
            update_file_metadata(
                input_file=mock_file,
                success=True,
                deleted_items=deleted,
                errors=errors,
            )

        call_kwargs = mock_update.call_args.kwargs
        delete_response = call_kwargs["custom_info"]["delete_response"]
        assert delete_response["deleted"]["logs"] == ["log1.json"]
        assert delete_response["deleted"]["acquisitions"] == ["group/project/file.json"]


class TestRun:
    def _make_mock_file(self):
        mock_file = MockFile(
            name="delete-request.json",
            modified=datetime(2024, 1, 14, tzinfo=timezone.utc),
        )
        mock_file.file_id = "file-id-123"  # type: ignore
        return mock_file

    def test_run_calls_process_request(self):
        """run() creates a processor and calls process_request exactly once."""
        mock_project = MagicMock()
        mock_project.proxy.get_lookup_path.return_value = "group/project/file.json"
        mock_file = self._make_mock_file()
        delete_request = DeleteRequest(
            ptid="adrc1010", module="uds", visitdate="2024-01-15", visitnum="1"
        )
        form_configs = MagicMock()
        identifiers_repo = MagicMock()

        mock_identifier = MagicMock()
        mock_processor = MagicMock()
        mock_processor.process_request.return_value = True
        mock_processor.deleted_items = DeletedItems()

        with (
            patch(
                "form_deletion_app.main.find_identifier", return_value=mock_identifier
            ),
            patch(
                "form_deletion_app.main.FormDeletionProcessor",
                return_value=mock_processor,
            ),
            patch("form_deletion_app.main.update_file_info"),
        ):
            run(
                project=mock_project,
                adcid=42,
                input_file=mock_file,
                delete_request=delete_request,
                form_configs=form_configs,
                identifiers_repo=identifiers_repo,
                check_sbsq_visits=True,
            )

        mock_processor.process_request.assert_called_once()

    def test_run_with_no_identifier(self):
        """run() proceeds correctly when find_identifier returns None."""
        mock_project = MagicMock()
        mock_project.proxy.get_lookup_path.return_value = "group/project/file.json"
        mock_file = self._make_mock_file()
        delete_request = DeleteRequest(
            ptid="adrc1010", module="uds", visitdate="2024-01-15", visitnum="1"
        )
        form_configs = MagicMock()
        identifiers_repo = MagicMock()

        mock_processor = MagicMock()
        mock_processor.process_request.return_value = False
        mock_processor.deleted_items = DeletedItems()

        captured_kwargs = {}

        def capture_processor(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_processor

        with (
            patch("form_deletion_app.main.find_identifier", return_value=None),
            patch(
                "form_deletion_app.main.FormDeletionProcessor",
                side_effect=capture_processor,
            ),
            patch("form_deletion_app.main.update_file_info"),
        ):
            run(
                project=mock_project,
                adcid=42,
                input_file=mock_file,
                delete_request=delete_request,
                form_configs=form_configs,
                identifiers_repo=identifiers_repo,
                check_sbsq_visits=True,
            )

        assert captured_kwargs.get("identifier") is None

    def test_run_updates_metadata_after_processing(self):
        """run() calls update_file_info with the processor result."""
        mock_project = MagicMock()
        mock_project.proxy.get_lookup_path.return_value = "group/project/file.json"
        mock_file = self._make_mock_file()
        delete_request = DeleteRequest(
            ptid="adrc1010", module="uds", visitdate="2024-01-15", visitnum="1"
        )
        form_configs = MagicMock()
        identifiers_repo = MagicMock()

        deleted = DeletedItems(logs=["some-log.json"])
        mock_processor = MagicMock()
        mock_processor.process_request.return_value = True
        mock_processor.deleted_items = deleted

        with (
            patch("form_deletion_app.main.find_identifier", return_value=None),
            patch(
                "form_deletion_app.main.FormDeletionProcessor",
                return_value=mock_processor,
            ),
            patch("form_deletion_app.main.update_file_info") as mock_update,
        ):
            run(
                project=mock_project,
                adcid=42,
                input_file=mock_file,
                delete_request=delete_request,
                form_configs=form_configs,
                identifiers_repo=identifiers_repo,
                check_sbsq_visits=True,
            )

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["custom_info"]["delete_response"]["state"] == "PASS"
        assert call_kwargs["custom_info"]["delete_response"]["deleted"]["logs"] == [
            "some-log.json"
        ]
