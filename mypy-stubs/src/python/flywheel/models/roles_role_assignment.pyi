from typing import List


class RolesRoleAssignment:
    def __init__(self, id:str, role_ids: List[str]) -> None: ...
    @property
    def id(self) -> str: ...
    @property
    def role_ids(self) -> List[str]: ...
