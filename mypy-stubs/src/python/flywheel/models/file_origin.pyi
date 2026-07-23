from typing import Any


class FileOrigin:

    @property
    def id(self) -> str:
        ...

    @property
    def type(self) -> str:
        ...

    def __getitem__(self, key: str) -> Any:
        ...
