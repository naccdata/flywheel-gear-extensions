from typing import Any, Dict, List

from flywheel.models.container_parents import ContainerParents


class FileEntry:

    @property
    def id(self) -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def mimetype(self) -> str:
        ...

    def get(self, key, default=None) -> Dict[str, Any]:
        ...

    @property
    def hash(self) -> str:
        ...

    @property
    def parents(self) -> ContainerParents:
        ...

    def read(self) -> str:
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

    def reload(self) -> FileEntry:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    @tags.setter
    def tags(self, tags: List[str]):
        ...

    def add_tag(self, tag, **kwargs):
        ...

    def delete_tag(self, tag, **kwargs):
        ...

    def update_info(self, *args, **kwargs):
        ...

    def update(self, *args, **kwargs):
        ...
