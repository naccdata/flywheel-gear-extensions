from typing import List

from flywheel.models.container_parents import ContainerParents
from flywheel.models.file_entry import FileEntry


class ContainerOutput:
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def parents(self) -> ContainerParents: ...

    @property
    def files(self) -> List[FileEntry]: ...
