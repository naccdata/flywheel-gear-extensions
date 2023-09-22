from typing import Optional

from .access_level import AccessLevel


class AccessPermission:

    def __init__(self, id: Optional[str],
                 access: Optional[AccessLevel]) -> None:
        ...

    @property
    def id(self) -> Optional[str]:
        ...

    @property
    def access(self) -> Optional[AccessLevel]:
        ...
