from .container_type import ContainerType


class FixedInput:

    def __init__(self, id: str, input: str, name: str, type: ContainerType,
                 version: int) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def input(self) -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def type(self) -> ContainerType:
        ...

    @property
    def version(self) -> int:
        ...
