from datetime import datetime
from typing import Any, Dict, Optional
from flywheel.finder import Finder
from flywheel.models.acquisition import Acquisition


class Session:

    @property
    def id(self) -> str:
        ...

    @property
    def label(self) -> str:
        ...

    @property
    def info(self) -> object:
        ...

    @property
    def timestamp(self) -> Optional[datetime]:
        ...

    def reload(self) -> 'Session':
        ...

    def update(self, map: Dict[str, Any]):
        ...

    @property
    def acquisitions(self) -> Finder[Acquisition]:
        ...

    def add_acquisition(self, label: str) -> Acquisition:
        ...
