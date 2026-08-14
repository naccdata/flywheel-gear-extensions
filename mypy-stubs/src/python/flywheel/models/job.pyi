from typing import Any


class Job:

    @property
    def id(self) -> str:
        ...

    @property
    def state(self) -> str:
        ...

    @property
    def retried(self) -> str:
        ...

    def __getitem__(self, key: str) -> Any:
        ...

    def reload(self) -> "Job":
        ...
