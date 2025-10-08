from typing import Optional

class RoleOutput:
    def __init__(
        self,
        id: Optional[str] = None,
        label: Optional[str] = None,
        in_use: Optional[bool] = None,
    ) -> None: ...

    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def in_use(self) -> bool: ...
