from typing import Any, Dict, List, Optional, TextIO, Union

from flywheel.client import Client
from flywheel.models.acquisition import Acquisition
from flywheel.models.file_entry import FileEntry
from flywheel.models.group import Group
from flywheel.models.session import Session
from flywheel_gear_toolkit.utils.metadata import Metadata

# container type names are listed in flywheel.models.container_type
Container = Union[Acquisition, Session, Group, FileEntry]


class GearToolkitContext:
    # TODO: this is probably wrong,
    def get_container_from_ref(self, ref: str) -> Container:
        ...

    def get_input_filename(self, name: str) -> str:
        ...

    @property
    def client(self) -> Client:
        ...

    @property
    def config(self) -> Dict[str, Any]:
        ...

    @property
    def destination(self) -> Dict[str, Any]:
        ...

    def get_destination_container(self) -> Container:
        ...

    def get_input(self, name: str) -> Optional[Dict[str, Any]]:
        ...

    def get_input_path(self, name: str) -> Optional[str]:
        ...

    def get_input_file_object(self, name: str) -> Dict[str, Any]:
        ...

    def get_input_file_object_value(self, name: str, key: str) -> List[str]:
        ...

    def __enter__(self) -> GearToolkitContext:
        ...

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any):
        ...

    def init_logging(self) -> None:
        ...

    def log_config(self) -> None:
        ...

    def open_output(self, name: str, mode: str, encoding: str) -> TextIO:
        ...

    def get_client(self) -> Client:
        ...

    @property
    def metadata(self) -> Metadata:
        ...

    @property
    def manifest(self) -> Dict[str, Any]:
        ...
