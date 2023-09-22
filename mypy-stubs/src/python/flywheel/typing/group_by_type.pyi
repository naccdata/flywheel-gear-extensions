from typing import Protocol, Sequence

from .group_by_column_type import GroupByColumnType


class GroupByType(Protocol):

    @property
    def columns(self) -> Sequence[GroupByColumnType]:
        ...
