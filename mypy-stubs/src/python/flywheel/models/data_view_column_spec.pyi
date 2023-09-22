from .accumulator import Accumulator
from .type_str import TypeStr


class DataViewColumnSpec:

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
