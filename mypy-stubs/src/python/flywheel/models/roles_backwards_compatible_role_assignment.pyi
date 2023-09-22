from typing import List


class RolesBackwardsCompatibleRoleAssignment:

    @property
    def id(self) -> str:
        ...

    @property
    def role_ids(self) -> List[str]:
        ...

    @property
    def access(self) -> str:
        ...
