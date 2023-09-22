from typing import Protocol


class RoleType(Protocol):

    @property
    def id(self) -> str:
        ...
