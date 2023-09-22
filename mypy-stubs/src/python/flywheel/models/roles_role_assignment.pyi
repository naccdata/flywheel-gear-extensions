from typing import List, Optional


class RolesRoleAssignment:

    def __init__(self, id: Optional[str],
                 role_ids: Optional[List[str]]) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def role_ids(self) -> List[str]:
        ...
