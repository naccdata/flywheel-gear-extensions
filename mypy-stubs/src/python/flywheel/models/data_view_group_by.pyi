from typing import Optional, Sequence

from .data_view_group_by_column import DataViewGroupByColumn


class DataViewGroupBy:

    def __init__(self,
                 columns: Optional[Sequence[DataViewGroupByColumn]]) -> None:
        ...

    @property
    def columns(self) -> Sequence[DataViewGroupByColumn]:
        ...
