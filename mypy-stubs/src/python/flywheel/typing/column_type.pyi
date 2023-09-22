from typing import Protocol

from ..models.accumulator import Accumulator
from ..models.type_str import TypeStr


class ColumnType(Protocol):

    @property
    def src(self) -> str:
        ...

    @property
    def dst(self) -> str:
        ...

    @property
    def type(self) -> TypeStr:
        ...

    @property
    def expr(self) -> str:
        ...

    @property
    def accumulator(self) -> Accumulator:
        ...
