from typing import List

from .access_permission import AccessPermission
from .project import Project


class Group:

    def __init__(self, id: str, label: str) -> None:
        ...

    @property
    def label(self) -> str:
        ...

    @property
    def id(self) -> str:
        ...

    def add_project(self, label: str) -> Project:
        ...

    def projects(self) -> List[Project]:
        ...

    @property
    def roles(self) -> List[str]:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    def add_tag(self, tag: str) -> None:
        ...

    @property
    def permissions(self) -> List[AccessPermission]:
        ...

    def add_permission(self, permission: AccessPermission) -> None:
        ...

    def update_permission(self, user_id: str,
                          permission: AccessPermission) -> None:
        ...
