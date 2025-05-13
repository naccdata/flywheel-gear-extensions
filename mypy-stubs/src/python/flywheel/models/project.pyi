from typing import Any, Dict, List, Optional

from flywheel.finder import Finder
from flywheel.models.subject import Subject

from ..file_spec import FileSpec
from ..typing.role_assignment import RoleAssignment
from .file_entry import FileEntry
from .project_parents import ProjectParents
from .roles_role_assignment import RolesRoleAssignment


class Project:

    def __init__(self, label: str, parents: ProjectParents) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def label(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    @property
    def group(self) -> str:
        ...

    @property
    def tags(self) -> List[str]:
        ...

    @property
    def permissions(self) -> List[RolesRoleAssignment]:
        ...

    @property
    def copyable(self) -> bool:
        ...

    @property
    def info(self) -> Dict[str, Any]:
        ...

    @property
    def subjects(self) -> Finder[Subject]:
        ...

    # TODO: determine return type
    def add_permission(self, permission: RoleAssignment) -> None:
        ...

    def update_permission(self, user_id: str,
                          permission: RoleAssignment) -> None:
        ...

    def add_tag(self, tag: str) -> None:
        ...

    def get_file(self, name: str) -> FileEntry:
        ...

    def read_file(self, name: str) -> bytes:
        ...

    # update takes *args, if used for other attributes add as needed
    # probably have to change types to Optional[str]
    def update(self,
               copyable: Optional[bool] = False,
               description: Optional[str] = '') -> None:
        ...

    # TODO: determine return type
    def upload_file(self, file: FileSpec) -> List[FileEntry]:
        ...

    def update_info(self, *args: Dict[str, Any]) -> None:
        ...

    def reload(self) -> Project:
        ...

    def add_subject(self, label: str) -> Subject:
        ...
