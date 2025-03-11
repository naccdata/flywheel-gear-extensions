"""Defines a factory function for creating a ViewBuilder."""
from typing import List, Optional, Tuple

from flywheel.view_builder import ViewBuilder
from pydantic import BaseModel


class ColumnModel(BaseModel):
    """A data model for a dataview column object consisting of the data source
    key and the label for the dataview."""
    data_key: str
    label: str

    def as_tuple(self) -> Tuple[str, str]:
        return (self.data_key, self.label)


def make_builder(*,
                 label: str,
                 description: str,
                 columns: List[ColumnModel],
                 container: str = 'subject',
                 filename: Optional[str] = None,
                 filter_str: Optional[str] = None,
                 match: str = 'all') -> ViewBuilder:
    """Factory to create a ViewBuilder using the ColumnModel."""

    builder = ViewBuilder(label=label,
                          description=description,
                          columns=[column.as_tuple() for column in columns],
                          container=container,
                          filename=filename,
                          filter=filter_str,
                          match=match,
                          process_files=False,
                          include_ids=False,
                          include_labels=False,
                          error_column=False)
    return builder.missing_data_strategy('drop-row')
