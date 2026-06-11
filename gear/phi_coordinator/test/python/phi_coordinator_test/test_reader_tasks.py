"""Unit tests for the ReaderTaskClient and its models."""

from unittest.mock import Mock

import pytest
from flywheel import ApiClient  # type: ignore
from phi_coordinator_app.reader_tasks import (
    FormResponseModel,
    ProtocolModel,
    ReaderTaskClient,
    ReaderTaskModel,
)


def _page(results: list[dict], total: int | None = None) -> dict:
    return {"results": results, "total": total if total is not None else len(results)}


@pytest.fixture
def api() -> Mock:
    """A mock Flywheel ApiClient."""
    return Mock(spec=ApiClient)


@pytest.fixture
def client(api: Mock) -> ReaderTaskClient:
    return ReaderTaskClient(api_client=api)


def _last_call(api: Mock) -> tuple:
    call = api.call_api.call_args
    return call.args, call.kwargs


class TestFindProtocols:
    def test_filters_by_label(self, api: Mock, client: ReaderTaskClient) -> None:
        api.call_api.return_value = _page(
            [
                {"_id": "p1", "label": "default_image_pii_detector_protocol"},
                {"_id": "p2", "label": "something-else"},
            ]
        )
        result = client.find_protocols("default_image_pii_detector_protocol")
        assert [p.id for p in result] == ["p1"]
        assert all(isinstance(p, ProtocolModel) for p in result)
        args, _ = _last_call(api)
        assert args == ("/read_task_protocols", "GET")


class TestIterUnprocessedCompletedTasks:
    def test_builds_filter_and_yields_models(
        self, api: Mock, client: ReaderTaskClient
    ) -> None:
        api.call_api.return_value = _page(
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
        args, kwargs = _last_call(api)
        assert args == ("/readertasks", "GET")
        filters = dict(q for q in kwargs["query_params"] if q[0] == "filter")
        assert filters["filter"] == (
            "status=Complete,protocol_id=p1,tags!=phi-coordinator"
        )


class TestGetResponses:
    def test_filters_by_task_id(self, api: Mock, client: ReaderTaskClient) -> None:
        api.call_api.return_value = _page(
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
        _, kwargs = _last_call(api)
        assert ("filter", "task_id=t1") in kwargs["query_params"]


class TestWrites:
    def test_set_task_status(self, api: Mock, client: ReaderTaskClient) -> None:
        client.set_task_status("t1", "Todo")
        args, kwargs = _last_call(api)
        assert args == ("/readertasks/t1", "PUT")
        assert kwargs["body"] == {"status": "Todo"}

    def test_add_task_tag_merges_existing(
        self, api: Mock, client: ReaderTaskClient
    ) -> None:
        task = ReaderTaskModel.model_validate({"_id": "t1", "tags": ["existing"]})
        client.add_task_tag(task, "phi-coordinator")
        args, kwargs = _last_call(api)
        assert args == ("/readertasks/t1", "PUT")
        assert kwargs["body"] == {"tags": ["existing", "phi-coordinator"]}

    def test_add_task_tag_noop_when_present(
        self, api: Mock, client: ReaderTaskClient
    ) -> None:
        task = ReaderTaskModel.model_validate(
            {"_id": "t1", "tags": ["phi-coordinator"]}
        )
        client.add_task_tag(task, "phi-coordinator")
        api.call_api.assert_not_called()

    def test_clear_response(self, api: Mock, client: ReaderTaskClient) -> None:
        client.clear_response("r1")
        args, kwargs = _last_call(api)
        assert args == ("/formresponses/r1", "PUT")
        assert kwargs["body"] == {"response_data": {}}
