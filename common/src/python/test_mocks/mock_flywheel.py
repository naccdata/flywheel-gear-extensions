"""Mocked classes of common Flywheel-related code for local testing.

Currently mocking is minimal, Flywheel objects in particular should
avoid getting called as much as possible for local testing due to their
complexity.
"""

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from flywheel.file_spec import FileSpec
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from pydantic import BaseModel, field_validator


class MockFile(FileEntry):
    """Pydantic to mock a Flywheel file object."""

    def __init__(
        self, name: str, info: Optional[Dict[str, Any]] = None, contents: str = ""
    ) -> None:
        info = info if info else {}
        super().__init__(name=name, info=info)
        self.contents = contents

    # name: str
    # info: Dict[str, Any] = {}
    # contents: str = ""

    @field_validator("info", mode="before")
    @classmethod
    def deep_copy_info(cls, info: Dict[str, Any]) -> Dict[str, Any]:
        """We need to deep copy info so it's "separated" from the local
        instance."""
        return copy.deepcopy(info)

    def reload(self, *args, **kwargs):
        return self

    def update_info(self, info: Dict[Any, Any], **kwargs) -> None:
        """Update info object."""
        self.info.update(info)

    def read(self, *args, **kwargs):
        """Read self by basically returning UTF-8 encoded JSON string."""
        return self.contents.encode("utf-8")


class MockProject(ProjectAdaptor):
    """Mocked class of the ProjectAdaptor."""

    def __init__(self, label: str):
        self._project = None  # type: ignore
        self._fw = None  # type: ignore
        self.__files: Dict[str, MockFile] = {}
        self.__label = label

    @property
    def files(self) -> List[FileEntry]:
        """Get files."""
        return list(self.__files.values())

    @property
    def label(self) -> str:
        return self.__label

    def get_file(self, name: str) -> Optional[FileEntry]:
        """Get the file if it exists."""
        return self.__files.get(name, None)

    def upload_file(self, file: Union[FileSpec, Dict[str, Any]]) -> None:
        """Add file to files; replacing as needed."""
        if isinstance(file, FileSpec):
            self.__files[file.name] = MockFile(name=file.name, contents=file.contents)  # type: ignore
        else:
            self.__files[file["name"]] = MockFile(
                name=file["name"], contents=file["contents"], info=file.get("info", {})
            )

    def reload(self, *args, **kwargs):
        return self


class MockParents(BaseModel):
    """Mock parents object for Flywheel containers."""

    session: Optional[str] = None
    acquisition: Optional[str] = None
    subject: Optional[str] = None
    project: Optional[str] = None


class MockParentRef(BaseModel):
    """Mock parent reference."""

    id: str
    type: str = "acquisition"


class MockSession(BaseModel):
    """Mock Flywheel session container."""

    id: str
    label: str
    parents: MockParents = MockParents()

    def reload(self, *args, **kwargs):
        return self


class MockAcquisition(BaseModel):
    """Mock Flywheel acquisition container."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    label: str
    parents: MockParents
    files: List[FileEntry] = []

    def reload(self, *args, **kwargs):
        return self


class MockFlywheelProxy(FlywheelProxy):
    """Mock FlywheelProxy for testing."""

    def __init__(self):
        """Initialize mock proxy."""
        self._containers: Dict[str, Any] = {}

    def add_container(self, container_id: str, container: Any) -> None:
        """Add a container to the mock proxy.

        Args:
            container_id: The container ID
            container: The container object
        """
        self._containers[container_id] = container

    def get_container_by_id(self, container_id: str) -> Any:
        """Get a container by ID.

        Args:
            container_id: The container ID

        Returns:
            The container object

        Raises:
            KeyError: If container not found
        """
        if container_id not in self._containers:
            raise KeyError(f"Container {container_id} not found")
        return self._containers[container_id]


def create_mock_file_with_parent(
    name: str,
    parent_id: str,
    info: Optional[Dict[str, Any]] = None,
    contents: str = "",
    created: Optional[datetime] = None,
) -> MockFile:
    """Create a mock file with parent reference.

    Args:
        name: File name
        parent_id: Parent container ID
        info: File info metadata
        contents: File contents
        created: Creation timestamp

    Returns:
        MockFile with parent reference
    """
    file = MockFile(name=name, info=info, contents=contents)
    file.parent_ref = MockParentRef(id=parent_id)  # type: ignore[assignment]
    if created:
        file.created = created  # type: ignore[misc]
    return file
