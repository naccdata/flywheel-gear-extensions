from typing import Protocol


class GroupByColumnType(Protocol):

    @property
    def src(self) -> str:
        ...

    @property
    def dst(self) -> str:
        ...
