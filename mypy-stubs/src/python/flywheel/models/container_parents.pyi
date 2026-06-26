from typing import Any
from flywheel.models.group import Group


class ContainerParents:

    @property
    def group(self) -> str:
        ...

    def get(self, key: str) -> Any:
        ...

    @property
    def project(self) -> str:
        ...

    @property
    def session(self) -> str:
        ...

    @property
    def subject(self) -> str:
        ...

    @property
    def acquisition(self) -> str:
        ...
