from datetime import datetime
from typing import Optional

from flywheel.models.file_origin import FileOrigin


class FileVersionOutput:

    @property
    def created(self) -> datetime:
        ...

    @property
    def deleted(self) -> Optional[datetime]:
        ...

    @property
    def file_id(self) -> str:
        ...

    @property
    def origin(self) -> FileOrigin:
        ...

    @property
    def restored_by(self) -> Optional[FileOrigin]:
        ...

    @property
    def restored_from(self) -> Optional[FileOrigin]:
        ...

    @property
    def version(self) -> int:
        ...
