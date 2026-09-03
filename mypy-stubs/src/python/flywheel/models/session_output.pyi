from datetime import datetime
from typing import Any, Dict, List, Optional

from flywheel.finder import Finder
from flywheel.models.acquisition import Acquisition
from flywheel.models.container_parents import ContainerParents
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject


class SessionOutput:

    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def group(self) -> str: ...

    @property
    def project(self) -> str: ...

    @property
    def parents(self) -> ContainerParents: ...

    @property
    def info(self) -> Dict[str, Any]: ...

    @property
    def subject(self) -> Subject: ...

    @property
    def tags(self) -> List[str]: ...

    @property
    def files(self) -> List[FileEntry]: ...

    @property
    def timestamp(self) -> Optional[datetime]: ...

    @property
    def container_type(self) -> str: ...

    def reload(self) -> "SessionOutput": ...

    def acquisitions(self) -> Finder[Acquisition]: ...

    def add_tag(self, tag: str, **kwargs: Any) -> None: ...

    def delete_tag(self, tag: str, **kwargs: Any) -> None: ...

    def update_info(self, info: Dict[str, Any], **kwargs: Any) -> None: ...
