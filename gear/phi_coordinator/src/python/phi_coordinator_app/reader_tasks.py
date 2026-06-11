"""Models and API client for Flywheel reader tasks and form responses.

Defines the pydantic models for protocols, tasks, and responses, and the
ReaderTaskClient that calls the reader-task and form-response REST
endpoints the high-level Flywheel client does not expose.
"""

import logging
from collections.abc import Iterator

from flywheel import ApiClient  # type: ignore
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

_PAGE_SIZE = 100
_AUTH = ["ApiKey"]
_JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class ProtocolModel(BaseModel):
    """A reader-task protocol (subset of fields used here)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(alias="_id")
    label: str | None = None


class ContainerRef(BaseModel):
    """Reference to a Flywheel container (e.g. a task or response parent)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = None
    type: str | None = None


class TaskParents(BaseModel):
    """Parent container ids of a reader task or form response."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    group: str | None = None
    project: str | None = None
    subject: str | None = None
    session: str | None = None
    acquisition: str | None = None
    file: str | None = None


class ReaderTaskModel(BaseModel):
    """A reader task (subset of fields used here)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(alias="_id")
    task_id: str | None = None
    status: str | None = None
    protocol_id: str | None = None
    form_id: str | None = None
    parent: ContainerRef | None = None
    parents: TaskParents | None = None
    tags: list[str] = Field(default_factory=list)


class FormResponseModel(BaseModel):
    """A form response (subset of fields used here)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(alias="_id")
    task_id: str | None = None
    form_id: str | None = None
    response_data: dict = Field(default_factory=dict)
    revision: int = 0


class ReaderTaskClient:
    """Reads and updates reader tasks / form responses via the raw FW API."""

    def __init__(self, api_client: ApiClient):
        """Wraps a Flywheel ApiClient for reader-task/form-response calls."""
        self.__api = api_client

    def _get(
        self,
        path: str,
        *,
        filter_str: str | None = None,
        limit: int | None = None,
        skip: int | None = None,
    ) -> dict:
        """Performs a GET against the FW API and returns the parsed body."""
        query: list[tuple[str, object]] = []
        if filter_str is not None:
            query.append(("filter", filter_str))
        if limit is not None:
            query.append(("limit", limit))
        if skip is not None:
            query.append(("skip", skip))
        return self.__api.call_api(
            path,
            "GET",
            query_params=query,
            auth_settings=_AUTH,
            response_type=object,
            _return_http_data_only=True,
        )

    def _put(self, path: str, body: dict) -> object:
        """Performs a PUT against the FW API with a JSON body."""
        return self.__api.call_api(
            path,
            "PUT",
            body=body,
            header_params=dict(_JSON_HEADERS),
            auth_settings=_AUTH,
            response_type=object,
            _return_http_data_only=True,
        )

    def find_protocols(self, label: str) -> list[ProtocolModel]:
        """Returns all reader-task protocols matching the given label."""
        protocols: list[ProtocolModel] = []
        skip = 0
        while True:
            page = self._get("/read_task_protocols", limit=_PAGE_SIZE, skip=skip)
            results = page.get("results", [])
            protocols.extend(ProtocolModel.model_validate(r) for r in results)
            skip += len(results)
            if len(results) < _PAGE_SIZE or skip >= page.get("total", skip):
                break
        return [p for p in protocols if p.label == label]

    def iter_unprocessed_completed_tasks(
        self, protocol_id: str, coordinated_tag: str
    ) -> Iterator[ReaderTaskModel]:
        """Yields Complete tasks for a protocol that lack the coordinated
        tag."""
        filter_str = (
            f"status=Complete,protocol_id={protocol_id},tags!={coordinated_tag}"
        )
        skip = 0
        while True:
            page = self._get(
                "/readertasks", filter_str=filter_str, limit=_PAGE_SIZE, skip=skip
            )
            results = page.get("results", [])
            for result in results:
                yield ReaderTaskModel.model_validate(result)
            skip += len(results)
            if len(results) < _PAGE_SIZE or skip >= page.get("total", skip):
                break

    def get_responses(self, task_id: str) -> list[FormResponseModel]:
        """Returns the form responses associated with a reader task id."""
        page = self._get(
            "/formresponses", filter_str=f"task_id={task_id}", limit=_PAGE_SIZE
        )
        return [FormResponseModel.model_validate(r) for r in page.get("results", [])]

    def set_task_status(self, task_id: str, status: str) -> None:
        """Sets a reader task's status (e.g. Todo, Complete)."""
        self._put(f"/readertasks/{task_id}", {"status": status})

    def add_task_tag(self, task: ReaderTaskModel, tag: str) -> None:
        """Adds a tag to a reader task, preserving existing tags."""
        existing = task.tags or []
        if tag in existing:
            return
        self._put(f"/readertasks/{task.id}", {"tags": [*existing, tag]})

    def clear_response(self, response_id: str) -> None:
        """Clears a form response's answer data so the form reads as
        unfilled."""
        self._put(f"/formresponses/{response_id}", {"response_data": {}})
