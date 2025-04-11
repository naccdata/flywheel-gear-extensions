from typing import Any, List, Optional

from flywheel.models.data_view import DataView


class ViewBuilder:

    def __init__(self,
                 label: Optional[str] = None,
                 description: Optional[str] = None,
                 public: Optional[bool] = None,
                 columns: Optional[List[Any]] = None,
                 container: Optional[str] = None,
                 filename: Optional[str] = None,
                 process_files: bool = True,
                 filter: Optional[str] = None,
                 include_ids: bool = True,
                 include_labels: bool = True,
                 match: Optional[str] = None,
                 error_column: bool = False) -> None:
        ...

    def build(self) -> DataView:
        ...

    def missing_data_strategy(self, value) -> 'ViewBuilder':
        ...
