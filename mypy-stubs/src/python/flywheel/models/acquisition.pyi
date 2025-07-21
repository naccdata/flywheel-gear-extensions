from typing import List, Dict

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

    def read_file(self, name: str) -> bytes:
        ...

    def get_file(self, name: str) -> FileEntry:
        ...

    def upload_file(self, file: FileSpec) -> List[Dict]:
        ...

    def reload(self) -> 'Acquisition':
        ...
