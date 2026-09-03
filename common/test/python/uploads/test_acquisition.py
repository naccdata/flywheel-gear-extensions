"""Tests acquisition file metadata helpers."""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock

import pytest
from flywheel.rest import ApiException
from uploads.acquisition import reset_visit_qc_metadata


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
