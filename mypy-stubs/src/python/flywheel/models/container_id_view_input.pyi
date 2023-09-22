from typing import Sequence

from ..typing.column_type import ColumnType
from ..typing.group_by_type import GroupByType
from .data_strategy import DataStrategy


class ContainerIdViewInput:

    def __init__(self, parent: str, label: str, description: str,
                 columns: Sequence[ColumnType], group_by: GroupByType,
                 filter: str, file_spec: object, include_ids: bool,
                 include_labels: bool, error_column: bool,
                 missing_data_strategy: DataStrategy, sort: bool,
                 id: str) -> None:
        ...
