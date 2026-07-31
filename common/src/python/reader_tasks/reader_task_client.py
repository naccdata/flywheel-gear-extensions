"""Models and API client for Flywheel reader tasks and form responses.

Defines the pydantic models for protocols, tasks, and responses, and the
ReaderTaskClient that calls the reader-task and form-response REST
endpoints the Flywheel SDK does not expose. Uses FWClient for transport,
following the convention for SDK-gap endpoints.
"""

import logging
from collections.abc import Iterator

from fw_client.client import FWClient
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

_PAGE_SIZE = 100

# Flywheel REST endpoints the SDK does not expose (FWClient takes the full
# /api path). Sub-resources are addressed as f"{_TASKS_PATH}/{task_id}".
_PROTOCOLS_PATH = "/api/read_task_protocols"
_TASKS_PATH = "/api/readertasks"
_RESPONSES_PATH = "/api/formresponses"


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
    """Reads and updates reader tasks / form responses via FWClient."""

    def __init__(self, fw_client: FWClient):
        """Initializes the client.

        Args:
          fw_client: the FWClient for the Flywheel instance
        """
        self.__fw = fw_client

    def _get(
        self,
        path: str,
        *,
        filter_str: str | None = None,
        limit: int | None = None,
        skip: int | None = None,
    ) -> dict:
        """Performs a GET against the FW API and returns the parsed body."""
        params: dict[str, str | int] = {}
        if filter_str is not None:
            params["filter"] = filter_str
        if limit is not None:
            params["limit"] = limit
        if skip is not None:
            params["skip"] = skip
        # FWClient.get returns the parsed JSON body, but the static
        # signature is inherited from httpx.Client (cf. flywheel_proxy)
        return self.__fw.get(path, params=params)  # type: ignore[return-value]

    def _put(self, path: str, body: dict) -> object:
        """Performs a PUT against the FW API with a JSON body."""
        return self.__fw.put(path, json=body)

    def find_protocols(self, label: str) -> list[ProtocolModel]:
        """Returns all reader-task protocols matching the given label.

        Args:
          label: the protocol label to match
        Returns:
          the protocols whose label equals the argument
        """
        protocols: list[ProtocolModel] = []
        skip = 0
        while True:
            page = self._get(_PROTOCOLS_PATH, limit=_PAGE_SIZE, skip=skip)
            results = page.get("results", [])
            protocols.extend(ProtocolModel.model_validate(r) for r in results)
            skip += len(results)
            if len(results) < _PAGE_SIZE or skip >= page.get("total", skip):
                break
        return [p for p in protocols if p.label == label]

    def iter_unprocessed_completed_tasks(
        self, protocol_id: str, coordinated_tag: str
    ) -> Iterator[ReaderTaskModel]:
        """Yields Complete tasks for a protocol that lack the coordinated tag.

        Args:
          protocol_id: the id of the reader-task protocol
          coordinated_tag: the tag marking already-processed tasks
        Yields:
          the tasks with status Complete and without the coordinated tag
        """
        filter_str = (
            f"status=Complete,protocol_id={protocol_id},tags!={coordinated_tag}"
        )
        skip = 0
        while True:
            page = self._get(
                _TASKS_PATH, filter_str=filter_str, limit=_PAGE_SIZE, skip=skip
            )
            results = page.get("results", [])
            for result in results:
                yield ReaderTaskModel.model_validate(result)
            skip += len(results)
            if len(results) < _PAGE_SIZE or skip >= page.get("total", skip):
                break

    def get_responses(self, task_id: str) -> list[FormResponseModel]:
        """Returns the form responses associated with a reader task id.

        Args:
          task_id: the reader task id
        Returns:
          the form responses for the task
        """
        page = self._get(
            _RESPONSES_PATH, filter_str=f"task_id={task_id}", limit=_PAGE_SIZE
        )
        return [FormResponseModel.model_validate(r) for r in page.get("results", [])]

    def set_task_status(self, task_id: str, status: str) -> None:
        """Sets a reader task's status (e.g. Todo, Complete).

        Args:
          task_id: the reader task id
          status: the status value to set
        """
        self._put(f"{_TASKS_PATH}/{task_id}", {"status": status})

    def add_task_tag(self, task: ReaderTaskModel, tag: str) -> None:
        """Adds a tag to a reader task, preserving existing tags.

        Does nothing if the task already has the tag.

        Args:
          task: the reader task
          tag: the tag to add
        """
        existing = task.tags or []
        if tag in existing:
            return
        self._put(f"{_TASKS_PATH}/{task.id}", {"tags": [*existing, tag]})

    def clear_response(self, response_id: str) -> None:
        """Clears a form response's answer data so the form reads as unfilled.

        Args:
          response_id: the form response id
        """
        self._put(f"{_RESPONSES_PATH}/{response_id}", {"response_data": {}})
