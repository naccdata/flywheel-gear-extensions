"""Unit tests for the ReaderTaskClient and its models."""

from unittest.mock import Mock

import pytest
from fw_client.client import FWClient
from reader_tasks.reader_task_client import (
    FormResponseModel,
    ProtocolModel,
    ReaderTaskClient,
    ReaderTaskModel,
)


def _page(results: list[dict], total: int | None = None) -> dict:
    return {"results": results, "total": total if total is not None else len(results)}


@pytest.fixture
def fw() -> Mock:
    """A mock FWClient."""
    return Mock(spec=FWClient)


@pytest.fixture
def client(fw: Mock) -> ReaderTaskClient:
    return ReaderTaskClient(fw_client=fw)


class TestFindProtocols:
    def test_filters_by_label(self, fw: Mock, client: ReaderTaskClient) -> None:
        fw.get.return_value = _page(
            [
                {"_id": "p1", "label": "default_image_pii_detector_protocol"},
                {"_id": "p2", "label": "something-else"},
            ]
        )
        result = client.find_protocols("default_image_pii_detector_protocol")
        assert [p.id for p in result] == ["p1"]
        assert all(isinstance(p, ProtocolModel) for p in result)
        fw.get.assert_called_once_with(
            "/api/read_task_protocols", params={"limit": 100, "skip": 0}
        )

    def test_paginates_until_total(self, fw: Mock, client: ReaderTaskClient) -> None:
        first_page = [{"_id": f"p{i}", "label": "phi"} for i in range(100)]
        fw.get.side_effect = [
            _page(first_page, total=101),
            _page([{"_id": "p100", "label": "phi"}], total=101),
        ]
        result = client.find_protocols("phi")
        assert len(result) == 101
        assert fw.get.call_count == 2
        fw.get.assert_called_with(
            "/api/read_task_protocols", params={"limit": 100, "skip": 100}
        )


class TestIterUnprocessedCompletedTasks:
    def test_builds_filter_and_yields_models(
        self, fw: Mock, client: ReaderTaskClient
    ) -> None:
        fw.get.return_value = _page(
            [
                {
                    "_id": "t1",
                    "task_id": "R-1-1",
                    "status": "Complete",
                    "parent": {"id": "f1", "type": "file"},
                },
            ]
        )
        tasks = list(client.iter_unprocessed_completed_tasks("p1", "phi-coordinator"))
        assert [t.id for t in tasks] == ["t1"]
        assert isinstance(tasks[0], ReaderTaskModel)
        fw.get.assert_called_once_with(
            "/api/readertasks",
            params={
                "filter": "status=Complete,protocol_id=p1,tags!=phi-coordinator",
                "limit": 100,
                "skip": 0,
            },
        )


class TestGetResponses:
    def test_filters_by_task_id(self, fw: Mock, client: ReaderTaskClient) -> None:
        fw.get.return_value = _page(
            [
                {
                    "_id": "r1",
                    "task_id": "t1",
                    "response_data": {"phi_radio": "yes"},
                    "revision": 2,
                },
            ]
        )
        responses = client.get_responses("t1")
        assert responses[0].response_data == {"phi_radio": "yes"}
        assert isinstance(responses[0], FormResponseModel)
        fw.get.assert_called_once_with(
            "/api/formresponses", params={"filter": "task_id=t1", "limit": 100}
        )


class TestWrites:
    def test_set_task_status(self, fw: Mock, client: ReaderTaskClient) -> None:
        client.set_task_status("t1", "Todo")
        fw.put.assert_called_once_with("/api/readertasks/t1", json={"status": "Todo"})

    def test_add_task_tag_merges_existing(
        self, fw: Mock, client: ReaderTaskClient
    ) -> None:
        task = ReaderTaskModel.model_validate({"_id": "t1", "tags": ["existing"]})
        client.add_task_tag(task, "phi-coordinator")
        fw.put.assert_called_once_with(
            "/api/readertasks/t1", json={"tags": ["existing", "phi-coordinator"]}
        )

    def test_add_task_tag_noop_when_present(
        self, fw: Mock, client: ReaderTaskClient
    ) -> None:
        task = ReaderTaskModel.model_validate(
            {"_id": "t1", "tags": ["phi-coordinator"]}
        )
        client.add_task_tag(task, "phi-coordinator")
        fw.put.assert_not_called()

    def test_clear_response(self, fw: Mock, client: ReaderTaskClient) -> None:
        client.clear_response("r1")
        fw.put.assert_called_once_with(
            "/api/formresponses/r1", json={"response_data": {}}
        )
