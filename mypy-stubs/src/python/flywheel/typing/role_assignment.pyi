from typing import List, Protocol


class RoleAssignment(Protocol):

    @property
    def id(self) -> str:
        ...

    @property
    def role_ids(self) -> List[str]:
        ...
