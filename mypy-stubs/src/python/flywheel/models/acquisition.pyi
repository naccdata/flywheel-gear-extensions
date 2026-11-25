from typing import Any, List, Dict

from flywheel.file_spec import FileSpec
from flywheel.models.file_entry import FileEntry


class Acquisition:

    def __init__(self, label: str) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def label(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def group(self) -> str:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    @property
    def files(self) -> List[FileEntry]:
        ...

    def read_file(self, name: str) -> bytes:
        ...

    def get_file(self, name: str) -> FileEntry:
        ...

    def upload_file(self, file: FileSpec) -> List[Dict]:
        ...

    @property
    def info(self) -> Dict[str, Any]:
        ...

    def update_info(self, info: Dict[str, Any], **kwargs: Any) -> None:
        ...

    def delete_file(self, name: str) -> None:
        ...

    def reload(self) -> 'Acquisition':
        ...
