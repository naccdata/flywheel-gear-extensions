from typing import Any, Dict, List, Optional

from flywheel.models.container_output import ContainerOutput
import pandas
from flywheel.models.file_entry import FileEntry
from flywheel.models.job import Job
from flywheel.models.session import Session
from flywheel.models.subject import Subject
from flywheel.models.viewer_app import ViewerApp

from .finder import Finder
from .models.acquisition import Acquisition
from .models.container_id_view_input import ContainerIdViewInput
from .models.container_output import ContainerOutput
from .models.data_view import DataView
from .models.deleted_result import DeletedResult
from .models.gear_rule import GearRule
from .models.gear_rule_input import GearRuleInput
from .models.group import Group
from .models.group_input import GroupInput
from .models.group_role import GroupRole
from .models.project import Project
from .models.project_settings_output import ProjectSettingsOutput
from .models.project_sharing_settings_project_settings_input import \
    ProjectSharingSettingsProjectSettingsInput
from .models.project_sharing_settings_project_settings_output import \
    ProjectSharingSettingsProjectSettingsOutput
from .models.role_output import RoleOutput
from .models.user import User
from .models.view_id_output import ViewIdOutput
from .typing.role_type import RoleType


class Client:

    def __init__(self, api_key: Optional[str]) -> None:
        ...

    @property
    def projects(self) -> Finder[Project]:
        ...

    @property
    def groups(self) -> Finder[Group]:
        ...

    @property
    def users(self) -> Finder[User]:
        ...

    @property
    def jobs(self) -> Finder[Job]:
        ...

    # the code says returns FileOutput but has no definition
    # documentation says returns FileEntry, so going with it
    def get_file(self, file_id: str) -> FileEntry:
        ...

    # type of group is actually GroupInput which has a common mixin with group
    def add_group(self, group: Group) -> str:
        ...

    def get_group(self, id: str) -> Group:
        ...

    def get_all_roles(self) -> List[RoleOutput]:
        ...

    # body in SDK is GroupRole, but use RoleType to allow passing RolesRole
    def add_role_to_group(self, group_id: str, body: RoleType) -> None:
        ...

    def get_project_rules(self, project_id: str) -> List[GearRule]:
        ...

    def add_project_rule(self, project_id: str,
                         body: GearRuleInput) -> GearRule:
        ...

    def remove_project_rule(self, project_id: str, rule_id: str) -> None:
        ...

    def add_user(self, user: User) -> str:
        ...

    def modify_user(self, user_id: str, body: Dict[str, str]) -> None:
        ...

    def get_views(self, view_id: str) -> List[DataView]:
        ...

    def add_view(self, container_id: str,
                 body: ContainerIdViewInput) -> ViewIdOutput:
        ...

    def modify_view(self, view_id: str, body: DataView) -> None:
        ...

    def delete_view(self, view_id: str) -> DeletedResult:
        ...

    def get_project_settings(self, project_id: str) -> ProjectSettingsOutput:
        ...

    # This is the formaly defined type
    #
    # def modify_project_settings(
    #     self, project_id: str, body: ProjectSharingSettingsProjectSettingsInput
    # ) -> ProjectSharingSettingsProjectSettingsOutput:
    #     ...
    #
    # This is the type that matches the working code
    def modify_project_settings(
        self, project_id: str, body: Dict[str, List[ViewerApp]]
    ) -> ProjectSharingSettingsProjectSettingsOutput:
        ...

    # return type is ConfigOut which seems to be JSON response
    def get_config(self, **kwargs) -> Dict[str, Any]:
        ...

    # these are methods forwarded to the Flywheel object by Client.__getattr__
    #
    def get_session(self, session_id: str) -> Session:
        ...

    def get_subject(self, subject_id: str) -> Subject:
        ...

    def read_view_dataframe(self, view: DataView,
                            container_id: str) -> pandas.DataFrame:
        ...

    def read_view_data(self, view, container_id, decode=True, **kwargs):
        """returns a file-like object where the contents can be read."""
        ...

    def get_project(self, id: str) -> Project:
        ...

    def get_acquisition(self, id: str) -> Acquisition:
        ...

    def get(self, id: str, **kwargs: Dict[str, Any]) -> ContainerOutput:
        ...

    # return type is ResolverOutput
    def lookup(self, path):
        ...
