from datetime import datetime
from typing import Any, Dict, List

from flywheel.models.file_origin import FileOrigin


class FileOutput:

    @property
    def id(self) -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def mimetype(self) -> str:
        ...

    @property
    def version(self) -> int:
        ...

    @property
    def info_exists(self) -> bool:
        ...

    @property
    def info(self) -> Dict[str, Any]:
        ...

    @property
    def origin(self) -> FileOrigin:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    @property
    def modified(self) -> datetime:
        ...

    def reload(self) -> FileOutput:
        ...

    def add_tag(self, tag, **kwargs):
        ...

    def add_tags(self, tags, **kwargs):
        ...

    def delete_tag(self, tag, **kwargs):
        ...
