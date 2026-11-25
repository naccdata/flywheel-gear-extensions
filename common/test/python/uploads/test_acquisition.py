"""Tests acquisition file metadata helpers."""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest
from flywheel.file_spec import FileSpec
from flywheel.rest import ApiException

from test_mocks.mock_flywheel import (
    MockAcquisition,
    MockParents,
    create_mock_acquisition_file,
)
from uploads.acquisition import replace_in_acquisition, reset_visit_qc_metadata


def _visit_file(
    *, info: Optional[Dict[str, Any]] = None, tags: Optional[List[str]] = None
) -> Mock:
    """Create a mock visit file with the given metadata and tags."""
    visit_file = Mock()
    visit_file.name = "NACC000001_FORMS-VISIT-2_UDS.json"
    visit_file.info = (
        info
        if info is not None
        else {
            "forms": {"json": {"ptid": "110001", "visitdate": "2024-03-15"}},
            "qc": {"form-qc-checker": {"validation": {"state": "FAIL"}}},
        }
    )
    visit_file.tags = list(tags) if tags else []
    return visit_file


class TestResetVisitQCMetadata:
    """Tests reset_visit_qc_metadata."""

    def test_clears_qc_and_validated_timestamp(self):
        """QC metadata is emptied and the validated timestamp is cleared."""
        visit_file = _visit_file()

        assert reset_visit_qc_metadata(visit_file)

        visit_file.update_info.assert_called_once_with(
            {"qc": {}, "validated-timestamp": ""}
        )

    def test_visit_data_not_in_payload(self):
        """The payload must not carry the visit data, which stays as is."""
        visit_file = _visit_file()

        assert reset_visit_qc_metadata(visit_file)

        payload = visit_file.update_info.call_args.args[0]
        assert "forms" not in payload

    def test_removes_only_status_tags(self):
        """Gear status tags are removed, unrelated tags are kept."""
        visit_file = _visit_file(
            tags=[
                "form-qc-checker-PASS",
                "file-validator-FAIL",
                "submission-completed",
                "form-transformer",
                "queued",
            ]
        )

        assert reset_visit_qc_metadata(visit_file)

        deleted = [call.args[0] for call in visit_file.delete_tag.call_args_list]
        assert sorted(deleted) == [
            "file-validator-FAIL",
            "form-qc-checker-PASS",
            "submission-completed",
        ]

    def test_no_tags(self):
        """A file without tags is handled without error."""
        visit_file = _visit_file(tags=[])

        assert reset_visit_qc_metadata(visit_file)

        visit_file.delete_tag.assert_not_called()

    @pytest.mark.parametrize("failing_call", ["update_info", "delete_tag"])
    def test_api_failure_returns_false(self, failing_call):
        """An API failure is reported rather than raised."""
        visit_file = _visit_file(tags=["form-qc-checker-PASS"])
        getattr(visit_file, failing_call).side_effect = ApiException(
            status=500, reason="boom"
        )

        assert not reset_visit_qc_metadata(visit_file)


def _file_spec() -> FileSpec:
    return FileSpec(name="receipt.csv", contents="a,b", content_type="text/csv")


def _acquisition(*, existing: bool = False, conflict: bool = False):
    files = (
        [create_mock_acquisition_file("receipt.csv", "a" * 24, "acq-1")]
        if existing
        else []
    )
    return MockAcquisition(
        id="acq-1",
        label="acq",
        parents=MockParents(),
        files=files,
        conflict_on_upload=conflict,
    )


class TestReplaceInAcquisition:
    """Tests replace_in_acquisition."""

    def test_no_conflict_uploads_once(self):
        """Without an existing file there is one upload and no delete."""
        acquisition = _acquisition()
        spec = _file_spec()

        replace_in_acquisition(acquisition, spec)

        assert acquisition.uploads == [spec]
        assert acquisition.deleted == []

    def test_conflict_deletes_then_uploads(self):
        """A 409 deletes the existing file and uploads again."""
        acquisition = _acquisition(existing=True, conflict=True)
        spec = _file_spec()

        replace_in_acquisition(acquisition, spec)

        assert acquisition.deleted == ["receipt.csv"]
        assert acquisition.uploads == [spec]

    def test_other_error_propagates_without_delete(self):
        """A non-409 error is raised and nothing is deleted."""
        acquisition = Mock()
        acquisition.upload_file.side_effect = ApiException(status=500, reason="boom")

        with pytest.raises(ApiException) as info:
            replace_in_acquisition(acquisition, _file_spec())

        assert info.value.status == 500
        acquisition.delete_file.assert_not_called()

    def test_delete_failure_propagates(self):
        """A failing delete is raised unchanged."""
        acquisition = Mock()
        acquisition.upload_file.side_effect = ApiException(status=409, reason="dup")
        acquisition.delete_file.side_effect = ApiException(status=500, reason="boom")

        with pytest.raises(ApiException) as info:
            replace_in_acquisition(acquisition, _file_spec())

        assert info.value.status == 500

    def test_second_upload_failure_propagates(self):
        """A failing second upload is raised after the delete."""
        acquisition = Mock()
        acquisition.upload_file.side_effect = [
            ApiException(status=409, reason="dup")
        ] * 4 + [ApiException(status=500, reason="boom")] * 4

        with pytest.raises(ApiException) as info:
            replace_in_acquisition(acquisition, _file_spec())

        assert info.value.status == 500
        acquisition.delete_file.assert_called_once_with("receipt.csv")
