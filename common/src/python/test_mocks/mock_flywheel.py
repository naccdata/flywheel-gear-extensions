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
        self,
        name: str,
        parent_id: str = "",
        info: Optional[Dict[str, Any]] = None,
        contents: str = "",
        created: Optional[datetime] = None,
        modified: Optional[datetime] = None,
    ) -> None:
        info = info if info else {}
        super().__init__(name=name, info=info)
        self.contents = contents
        self.created = created if created is not None else datetime.now()
        self.__modified = modified if modified is not None else datetime.now()
        self.__parent_id = parent_id

    # name: str
    # info: Dict[str, Any] = {}
    # contents: str = ""

    @property
    def modified(self):
        return self.__modified

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


class MockProject(BaseModel):
    """Mock Flywheel project object."""

    id: str = "mock-project-id"
    label: str = "mock-project"
    group: str = "mock-group"
    info: Dict[str, Any] = {}

    def reload(self, *args, **kwargs):
        return self


class MockProjectAdaptor(ProjectAdaptor):
    """Mocked class of the ProjectAdaptor."""

    def __init__(
        self,
        label: str,
        files: Optional[Union[dict[str, MockFile], List[FileEntry]]] = None,
        info: Optional[dict[str, Any]] = None,
        group: Optional[str] = None,  # Accept but ignore for compatibility
    ):
        # Set default pipeline_adcid if not provided
        project_info = info if info else {"pipeline_adcid": 123}
        if "pipeline_adcid" not in project_info:
            project_info["pipeline_adcid"] = 123

        # Use provided group or default
        project_group = group if group else "mock-group"

        self._project = MockProject(label=label, group=project_group, info=project_info)  # type: ignore
        self._fw = None  # type: ignore

        # Handle files as either dict or list
        if files is None:
            self.__files: dict[str, FileEntry] = {}
        elif isinstance(files, dict):
            self.__files = files  # type: ignore
        else:
            # Convert list to dict using file names as keys
            self.__files = {file.name: file for file in files}

        self.__label = label

    @property
    def files(self) -> List[FileEntry]:
        """Get files."""
        return list(self.__files.values())

    @property
    def label(self) -> str:
        return self.__label

    @property
    def group(self) -> str:
        return self._project.group

    @property
    def id(self) -> str:
        return self._project.id

    def get_file(self, name: str) -> Optional[FileEntry]:
        """Get the file if it exists."""
        return self.__files.get(name, None)

    def add_file(self, file: FileEntry) -> None:
        self.__files[file.name] = file

    def upload_file(self, file: Union[FileSpec, Dict[str, Any]]) -> None:
        """Add file to files; replacing as needed."""
        if isinstance(file, FileSpec):
            mock_file = MockFile(name=file.name, contents=file.contents)  # type: ignore
            self.__files[file.name] = mock_file
        else:
            mock_file = MockFile(
                name=file["name"], contents=file["contents"], info=file.get("info", {})
            )
            self.__files[file["name"]] = mock_file

    def upload_file_contents(
        self, *, filename: str, contents: str, content_type: str = "text"
    ) -> Optional[FileEntry]:
        """Uploads a file to the project using filename and string contents.

        Args:
            filename: the file name
            contents: the string contents of the file
            content_type: the MIME content type (defaults to "text")

        Returns:
            the uploaded file entry, or None if upload failed
        """
        mock_file = MockFile(name=filename, contents=contents)
        self.__files[filename] = mock_file
        return mock_file

    def get_matching_files(self, query: str) -> List[FileEntry]:
        """Mock implementation of get_matching_files.

        Supports basic filtering by name pattern for QC status logs.
        """
        # Simple implementation: filter by name pattern
        if "qc-status.log" in query:
            return [f for f in self.files if f.name.endswith("_qc-status.log")]
        # Default: return all files
        return self.files

    def subjects(self):
        """Return empty list of subjects for testing."""
        return []

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
    modified: Optional[datetime] = None,
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
    file = MockFile(
        name=name, info=info, contents=contents, created=created, modified=modified
    )
    file.parent_ref = MockParentRef(id=parent_id)  # type: ignore[assignment]
    return file


def create_mock_project_adaptor(
    label: str = "ingest-form-test",
    group: str = "test-center",
    pipeline_adcid: int = 123,
) -> MockProjectAdaptor:
    """Create a basic mock ProjectAdaptor for simple tests.

    Args:
        label: Project label
        group: Group/center name
        pipeline_adcid: Pipeline ADCID

    Returns:
        MockProject instance configured with the provided parameters
    """
    return MockProjectAdaptor(label=label)
