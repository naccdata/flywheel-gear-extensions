from typing import Any, List, Optional

from .data_strategy import DataStrategy
from .data_view_column_spec import DataViewColumnSpec
from .data_view_file_spec import DataViewFileSpec
from .data_view_group_by import DataViewGroupBy


class DataView:

    @property
    def _id(self) -> Optional[str]:
        ...

    @_id.setter
    def _id(self, id: Optional[str]) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def parent(self) -> str:
        ...

    @parent.setter
    def parent(self, str) -> None:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def columns(self) -> List[DataViewColumnSpec]:
        ...

    @property
    def group_by(self) -> DataViewGroupBy:
        ...

    @property
    def filter(self) -> str:
        ...

    @property
    def file_spec(self) -> DataViewFileSpec:
        ...

    @property
    def include_ids(self) -> bool:
        ...

    @property
    def include_labels(self) -> bool:
        ...

    @property
    def error_column(self) -> bool:
        ...

    @property
    def missing_data_strategy(self) -> DataStrategy:
        ...

    @property
    def sort(self) -> bool:
        ...

    def get(self, key: str) -> Any:
        ...

    @property
    def label(self) -> str:
        ...
