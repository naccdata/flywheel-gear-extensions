from typing import Sequence

from .group_by_column import GroupByColumn


class GroupBy:

    @property
    def columns(self) -> Sequence[GroupByColumn]:
        ...
