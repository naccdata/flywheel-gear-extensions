"""Tests for the form deletion models."""

from typing import List

from deletions.models import DeletedItems, DeleteInfoModel, DeleteResponse


def create_info(logs: List[str]) -> DeleteInfoModel:
    return DeleteInfoModel(
        delete_response=DeleteResponse(deleted=DeletedItems(logs=logs), state="PASS")
    )


class TestGetDeletedVisitsList:
    def test_no_deleted_items(self):
        info = DeleteInfoModel(delete_response=DeleteResponse(state="PASS"))
        assert info.get_deleted_visits_list() is None

    def test_qc_status_logs(self):
        info = create_info(
            [
                "adrc_1010_2024-01-15_1_uds_qc-status.log",
                "1010_2024-01-15_np_qc-status.log",
            ]
        )
        assert info.get_deleted_visits_list() == (
            "PTID=adrc_1010, Module=UDS, Date=2024-01-15, Visit Number=1\n"
            "PTID=1010, Module=NP, Date=2024-01-15"
        )

    def test_any_log_suffix(self):
        info = create_info(
            [
                "1010_2024-01-15_1_uds_update-request.log",
                "1010_2024-01-15_np_updates.log",
            ]
        )
        assert info.get_deleted_visits_list() == (
            "PTID=1010, Module=UDS, Date=2024-01-15, Visit Number=1\n"
            "PTID=1010, Module=NP, Date=2024-01-15"
        )

    def test_non_log_files_skipped(self):
        info = create_info(
            [
                "1010_2024-01-15_1_uds_qc-status.txt",
                "1010_2024-01-15_1_uds_qc-status.log.bak",
            ]
        )
        assert info.get_deleted_visits_list() is None
