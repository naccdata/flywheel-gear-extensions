from typing import List

from flywheel.models.file_entry import FileEntry


class AcquisitionListOutput:
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def files(self) -> List[FileEntry]: ...
