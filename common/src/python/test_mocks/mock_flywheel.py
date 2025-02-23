"""
Mocked classes of common Flywheel-related code for local testing.

Currently mocking is minimal, Flywheel objects in particular
should avoid getting called as much as possible for local testing
due to their complexity.
"""
import copy
from flywheel.file_spec import FileSpec
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from pydantic import BaseModel, field_validator
from typing import Any, Dict, Optional


class MockFile(BaseModel):
    """Pydantic to mock a Flywheel file object."""
    name: str
    info: Optional[Dict[str, Any]] = {}
    contents: Optional[str] = ''

    @field_validator('info', mode='before')
    @classmethod
    def deep_copy_info(cls, info: str) -> Dict[str, Any]:
        """We need to deep copy info so it's "separated" from the
        local instance."""
        return copy.deepcopy(info)

    def reload(self, *args, **kwargs):
        return self

    def update_info(self, info: Dict[Any, Any], **kwargs):
        """Update info object."""
        self.info.update(info)

    def read(self, *args, **kwargs):
        """Read self by basically returning UTF-8 encoded JSON string."""
        return self.contents.encode('utf-8')


class MockProject(ProjectAdaptor):
    """Mocked class of the ProjectAdaptor."""

    def __init__(self):
        super().__init__(project=None, proxy=None)
        self.__files: Dict[str, MockFile] = {}

    @property
    def files(self) -> Dict[str, MockFile]:
        """Get files."""
        return self.__files

    def get_file(self, name: str, *args, **kwargs):
        """Get the file if it exists."""
        return self.__files.get(name, None)

    def upload_file(self, file: FileSpec, *args, **kwargs):
        """Add file to files; replacing as needed."""
        self.__files[file.name] = MockFile(name=file.name,
                                           contents=file.contents)

    def reload(self, *args, **kwargs):
        return self
