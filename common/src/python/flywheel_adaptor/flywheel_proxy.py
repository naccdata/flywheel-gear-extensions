# pylint: disable=too-many-lines
"""Defines project creation functions for calls to Flywheel."""

import json
import logging
from codecs import StreamReader
from json.decoder import JSONDecodeError
from typing import Any, Dict, Iterable, List, Literal, Optional, Self, Sequence

import flywheel
from flywheel import (
    Client,
    ContainerIdViewInput,
    DataView,
    GearRule,
    GearRuleInput,
    ViewIdOutput,
)
from flywheel.models.access_permission import AccessPermission
from flywheel.models.acquisition import Acquisition
from flywheel.models.container_output import ContainerOutput
from flywheel.models.file_entry import FileEntry
from flywheel.models.group_role import GroupRole
from flywheel.models.job import Job
from flywheel.models.project_parents import ProjectParents
from flywheel.models.role_output import RoleOutput
from flywheel.models.roles_role_assignment import RolesRoleAssignment
from flywheel.models.subject import Subject
from flywheel.models.user import User
from flywheel.rest import ApiException
from flywheel.view_builder import ViewBuilder
from fw_client.client import FWClient
from fw_utils import AttrDict
from utils.decorators import api_retry

from flywheel_adaptor.subject_adaptor import SubjectAdaptor

log = logging.getLogger(__name__)


class FlywheelError(Exception):
    """Exception class for Flywheel errors."""


# pylint: disable=(too-many-public-methods)
class FlywheelProxy:
    """Defines a proxy object for group and project creation on a Flywheel
    instance."""

    def __init__(
        self, client: Client, fw_client: Optional[FWClient] = None, dry_run: bool = True
    ) -> None:
        """Initializes a flywheel proxy object.

        Args:
          client: the Flywheel SDK client
          fw-client: the fw-client client
          dry_run: whether proxy will be used for a dry run
        """
        self.__fw = client
        self.__fw_client = fw_client
        self.__dry_run = dry_run
        self.__project_roles: Optional[dict[str, RoleOutput]] = None
        self.__project_admin_role: Optional[RoleOutput] = None

    @property
    def dry_run(self):
        """Indicates whether proxy is set for a dry run.

        Returns:
            True if proxy is set for a dry run. False otherwise.
        """
        return self.__dry_run

    def find_projects(
        self, *, group_id: str, project_label: str
    ) -> List[flywheel.Project]:
        """Finds a flywheel project with a given label, within a group ID if
        specified. Otherwise it's site wide.

        Args:
            project_label: the project label to search for
            group_id: the group ID the project may be in

        Returns:
            existing: a list of all matching projects.
        """
        return self.__fw.projects.find(
            f"parents.group={group_id},label={project_label}"
        )

    def find_groups(self, group_id: str) -> List[flywheel.Group]:
        """Searches for and returns a group if it exists.

        Args:
            group_id: the ID to search for

        Returns:
            the group (or empty list if not found)
        """
        try:
            return self.__fw.groups.find(f"_id={group_id}")
        except ApiException as error:
            raise FlywheelError(f"Cannot get group {group_id}: {error}") from error

    def find_group(self, group_id: str) -> Optional["GroupAdaptor"]:
        """Returns group for group id.

        Args:
          group_id: the group ID
        Returns:
          group with ID if exists, None otherwise
        """
        groups = self.find_groups(group_id)
        if not groups:
            return None

        return GroupAdaptor(group=groups[0], proxy=self)

    def find_groups_by_tag(self, tag_pattern: str) -> List[flywheel.Group]:
        """Searches for groups with tags matching the pattern.

        Args:
          tag_pattern: raw string regex pattern

        Returns:
          the list of groups
        """
        return self.__fw.groups.find(f"tags=~{tag_pattern}")

    def find_user(self, user_id: str) -> Optional[flywheel.User]:
        """Searches for and returns a user if it exists.

        Args:
            user_id: the ID to search for

        Returns:
            a list with the user, or None if not found
        """
        return self.__fw.users.find_first(f"_id={user_id}")

    def add_user(self, user: flywheel.User) -> str:
        """Adds the user and returns the user id.

        Note: the user ID and email have to be the same here.
        Update using set_user_email after the user has been added.

        Args:
          user: the user to add
        Returns:
          the user id for the user added
        """
        if self.dry_run:
            log.info("Dry run: would create user %s", user.id)
            assert user.id
            return user.id

        try:
            return self.__fw.add_user(user)
        except ApiException as error:
            raise FlywheelError(f"Failed to add user: {error}") from error

    def set_user_email(self, user: flywheel.User, email: str) -> None:
        """Sets user email on client.

        Args:
          user: local instance of user
          email: email address to set
        """
        assert user.id
        if self.dry_run:
            log.info("Dry run: would set user %s email to %s", user.id, email)
            return

        self.__fw.modify_user(user.id, {"email": email})

    def get_file(self, file_id: str) -> FileEntry:
        """Returns file object with the file ID.

        Args:
          file_id: the ID of the file
        Returns:
          file object for file with ID
        """
        return self.__fw.get_file(file_id)

    def get_files(self, query: str) -> list[FileEntry]:
        return self.__fw.files.find(query)

    def get_file_group(self, file_id: str) -> str:
        """Returns the group ID for the file.

        Args:
          file_id: the file ID
        Returns:
          the group ID for the file
        """
        file = self.get_file(file_id)
        return file.parents.group

    def get_group(self, *, group_id: str, group_label: str) -> flywheel.Group:
        """Returns the flywheel group with the given ID and label.

        If the group already exists, returns that group.
        Otherwise, creates a new group.

        if self.dry_run is true, creates a dummy object

        Args:
          group_id: the group ID to create
          group_label: the group label to create

        Returns:
          group: the created group
        Raises:
          FlywheelError if the group exists
        """
        group_list = self.find_groups(group_id)
        if group_list:
            return group_list[0]

        conflict = self.__fw.groups.find_first(
            f"label=~^{group_label.replace(',', '.')}$"
        )
        if conflict:
            raise FlywheelError(f"Group with label {group_label} exists: {conflict.id}")

        if self.__dry_run:
            log.info("Dry Run: would create group %s", group_id)
            return flywheel.Group(label=group_label, id=group_id)

        log.info("creating group...")
        # This just returns a string of the group ID
        try:
            added_group_id = self.__fw.add_group(flywheel.Group(group_id, group_label))
        except ApiException as error:
            log.error(
                (
                    "Group %s creation failed. "
                    "Group likely exists, but user does not have permission"
                ),
                group_label,
            )
            raise FlywheelError(f"Failed to create group {group_label}") from error

        # we must fw.get_group() with ID string to get the actual Group object.
        group = self.__fw.get_group(added_group_id)
        log.info("success")

        return group

    def get_project(
        self, *, group: flywheel.Group, project_label: str
    ) -> Optional[flywheel.Project]:
        """Given a flywheel project label and optional group ID, search for the
        project, and create it if it doesn't exist returns the project, found
        or created.

        Args:
            project_label: the project label to find or create
            group_id: the group id the project is in - required if creating

        Returns:
            project: the found or created project
        """
        if not group:
            log.error("Attempted to create a project %s without a group", project_label)
            return None

        project = group.projects.find_first(f"label={project_label}")
        if project:
            log.info("Project %s/%s exists", group.id, project_label)
            return project

        project_ref = f"{group.id}/{project_label}"
        if self.__dry_run:
            log.info("Dry Run: would create project %s", project_ref)
            return flywheel.Project(
                label=project_label, parents=ProjectParents(group=group.id)
            )

        log.info("creating project %s", project_ref)
        try:
            project = group.add_project(label=project_label)
        except ApiException as exc:
            log.error("Failed to create project %s: %s", project_ref, exc)
            return None
        log.info("success")

        return project

    def get_project_by_id(self, project_id: str) -> Optional[flywheel.Project]:
        """Returns a project with the given ID.

        Args:
          project_id: the ID for the project
        Returns:
          the project with the ID if exists, None otherwise
        """
        return self.__fw.projects.find_first(f"_id={project_id}")

    def get_pipeline(self, adcid: int) -> list["ProjectAdaptor"]:
        """Returns the project adaptors for projects with pipeline ADCID set to
        the ADCID.

        Args:
          adcid: the ADCID
        Returns:
          the list of projects identified with ADCID as pipeline ADCID
        """
        projects = self.__fw.projects.find(f"info.pipeline_adcid={adcid}")

        return [ProjectAdaptor(project=project, proxy=self) for project in projects]

    def get_roles(self) -> dict[str, RoleOutput]:
        """Gets all user roles for the FW instance.

        Does not include access roles for Groups.
        """
        if not self.__project_roles:
            all_roles = self.__fw.get_all_roles()
            self.__project_roles = {role.label: role for role in all_roles}
        return self.__project_roles

    def get_role(self, label: str) -> Optional[RoleOutput]:
        """Gets project role by label.

        Args:
          label: the name of the role
        Returns:
          the role with the name if one exists. None, otherwise
        """
        role_map = self.get_roles()
        return role_map.get(label)

    def get_user_roles(self, role_names: Sequence[str]) -> List[RoleOutput]:
        """Get the named roles .

        Returns all roles matching a name in the list.
        Logs a warning if a name is not matched.

        Args:
          role_names: the role names
        Returns:
          the list of roles with the names
        """
        role_list = []
        for name in role_names:
            role = self.get_role(name)
            if role:
                role_list.append(role)
            else:
                log.warning("no such role %s", name)
        return role_list

    def get_admin_role(self) -> Optional[RoleOutput]:
        """Gets admin role."""
        if not self.__project_admin_role:
            self.__project_admin_role = self.get_role("admin")
        return self.__project_admin_role

    def add_group_role(self, *, group: flywheel.Group, role: GroupRole) -> None:
        """Add role to the group.

        Args:
          group: the group
          role: the role
        """
        if role.id in group.roles:
            return

        if self.dry_run:
            log.info("Dry run: would add role %s to group %s", role.id, group.label)
            return

        self.__fw.add_role_to_group(group.id, role)

    def get_project_gear_rules(self, project: flywheel.Project) -> List[GearRule]:
        """Get the gear rules from the given project.

        Args:
          project: the flywheel project

        Returns:
          the gear rules
        """
        return self.__fw.get_project_rules(project.id)

    def add_project_rule(
        self, *, project: flywheel.Project, rule_input: GearRuleInput
    ) -> None:
        """Forwards call to the FW client."""
        if self.dry_run:
            log.info("Would add rule %s to project %s", rule_input, project.label)
            return

        self.__fw.add_project_rule(project.id, rule_input)

    def remove_project_gear_rule(
        self, *, project: flywheel.Project, rule: GearRule
    ) -> None:
        """Removes the gear rule from the project.

        Args:
          project: the project
          rule: the gear rule
        """
        if self.dry_run:
            log.info(
                "Dry run: would remove rule %s from project %s",
                rule.name,
                project.label,
            )
            return

        self.__fw.remove_project_rule(project.id, rule.id)

    def get_dataviews(self, project: flywheel.Project) -> List[DataView]:
        """Get the dataviews for the project.

        Args:
          project: the project
        Returns:
          the dataviews for the project
        """

        dataviews = self.__fw.get_views(project.id)
        return [view for view in dataviews if view.parent != "site"]

    def add_dataview(
        self, *, project: flywheel.Project, viewinput: ContainerIdViewInput
    ) -> ViewIdOutput:
        """Adds the data view to the enclosed project.

        Args:
          project: the project to which to add the data view
          viewinput: the object representing the data view
        """
        # TODO: setup dry run for add_dataview
        # if self.dry_run:
        #     log.info("Dry run: would add %s to project %s", viewinput,
        #              project.label)
        #     return ""

        return self.__fw.add_view(project.id, viewinput)

    def modify_dataview(self, *, source: DataView, destination: DataView) -> None:
        """Updates the destination data view by copying from the source view.

        Args:
          source: the source DataView
          destination: the DataView to modify
        """
        if self.dry_run:
            # TODO: add detail to dry run message
            log.info("Dry run: would modify data view")
            return

        temp_id = source._id  # noqa: SLF001
        temp_parent = source.parent
        source._id = None  # noqa: SLF001
        source.parent = destination.parent
        self.__fw.modify_view(destination.id, source)
        source._id = temp_id  # noqa: SLF001
        source.parent = temp_parent

    def delete_dataview(self, view: DataView) -> bool:
        """Removes the indicated dataview.

        Args:
          view: the dataview to remove
        Returns:
          True if the dataview is deleted, False otherwise
        """
        if self.dry_run:
            log.info("Dry run: would delete dataview %s", view)
            return False

        result = self.__fw.delete_view(view.id)
        return bool(result.deleted)

    # def get_project_apps(self, project: flywheel.Project) -> List[ViewerApp]:
    #     """Returns the viewer apps for the project.

    #     Args:
    #       project: the project
    #     Returns:
    #       The list of apps for the project
    #     """
    #     settings = self.__fw.get_project_settings(project.id)
    #     if not settings:
    #         return []

    #     return settings.viewer_apps

    def get_project_settings(self, project: flywheel.Project) -> AttrDict:
        """Returns the settings object for the project.

        Args:
          project: the project
        Returns:
          the project settings
        """
        assert self.__fw_client, "Requires FWClient to be instantiated"
        return self.__fw_client.get(f"/api/projects/{project.id}/settings")  # type: ignore

    def set_project_settings(
        self, *, project: flywheel.Project, settings: AttrDict
    ) -> None:
        """Sets the project settings to the argument.

        Args:
          project: the project
          settings: the settings dictionary
        """
        assert self.__fw_client, "Requires FWClient to be instantiated"
        self.__fw_client.put(url=f"/api/projects/{project.id}/settings", json=settings)

    def get_project_apps(self, project: flywheel.Project) -> List[AttrDict]:
        """Returns the viewer apps for the project.

        Note: Temporary fix using FWClient because flywheel-sdk doesn't manage
        type of viewer_apps.

        Args:
          project: the project
        """
        settings = self.get_project_settings(project)
        if not settings:
            return []

        return settings.viewer_apps  # type: ignore

    # def set_project_apps(self, *, project: flywheel.Project,
    #                      apps: List[ViewerApp]):
    #     """Sets the apps to the project settings to the list of apps.

    #     Note: this will replace any existing apps

    #     Args:
    #       project: the project
    #       apps: the list of viewer apps
    #     """
    #     if self.dry_run:
    #         log.info('Dry run: would set viewer %s in project %s', apps,
    #                  project.label)
    #         return

    #     self.__fw.modify_project_settings(project.id, {"viewer_apps": apps})

    def set_project_apps(
        self, *, project: flywheel.Project, apps: List[AttrDict]
    ) -> None:
        """Sets the viewer apps of the project to the list of apps.

        Note: this will replace any existing apps.

        Note: temporary fix using FWClient because flywheel-sdk doesn't manage
        type of viewer_apps.

        Args:
          project: the project
          apps: the list of viewer apps
        """
        assert self.__fw_client, "Requires FWClient to be instantiated"
        if self.dry_run:
            log.info("Dry run: would set viewer %s in project %s", apps, project.label)
            return

        settings = self.get_project_settings(project)
        if not settings:
            log.warning("Project %s has no settings", project.label)
            return

        settings["viewer_apps"] = apps  # type: ignore
        self.set_project_settings(project=project, settings=settings)

    def get_site(self):
        """Returns URL for site of this instance."""
        return self.__fw.get_config()["site"]["redirect_url"]

    def get_lookup_path(self, container) -> str:
        """Returns the path to the container.

        Args:
          container: the container
        Returns:
          the path to the container
        """
        assert container.parents, "expect parents for container"

        path = "fw://"
        container_name = get_name(container)
        ancestors = container.parents

        # names of containers of FW hierarchy listed in order minus files
        levels = ["group", "project", "subject", "session", "acquisition", "analysis"]
        for level in levels:
            ancestor_id = ancestors.get(level, None)
            if ancestor_id:
                # gears invoked by a gear rule does not have access to group
                if level == "group":
                    ancestor_name = ancestor_id
                else:
                    ancestor = self.__fw.get(ancestor_id)
                    ancestor_name = get_name(ancestor)
                path = f"{path}{ancestor_name}/"

        return f"{path}{container_name}"

    def get_acquisition(self, acq_id: str) -> Acquisition:
        """Returns acquisition object for the acq_id.

        Args:
          acq_id: the ID of the acquisition

        Returns:
          Acquisition object for the given ID
        """
        return self.__fw.get_acquisition(acq_id)

    def lookup_gear(self, gear_name: str) -> Any:
        """Lookup the specified Flywheel gear.

        Args:
            gear_name: gear name

        Returns:
            Any: Flywheel gear object
        """
        return self.__fw.lookup(f"gears/{gear_name}")

    def retry_job(self, job_id: str) -> Optional[str]:
        """Retry a job.

        The job must have a state of 'failed', and must not have already been retried.

        Args:
            job_id: ID of the job to retry

        Returns:
            Optional[str]: ID of the new job or None
        """
        try:
            return self.__fw.retry_job(job_id)
        except ApiException as error:
            log.error("Failed to retry the job %s - %s", job_id, error)
            return None

    def find_job(self, search_str: str, **kwargs) -> Optional[Job]:
        """Find the first Job matching the search string.

        Args:
            search_str: parameters to search (e.g. 'state=failed')

        Returns:
            Job: Flywheel Job object if found, else None
        """
        return self.__fw.jobs.find_first(search_str, **kwargs)

    def find_jobs(self, search_str: str) -> List[Job]:
        """Find all jobs matching the search string.

        Args:
            search_str: parameters to search (e.g. 'state=failed')

        Returns:
            Job: List of Flywheel Job objects found
        """
        return self.__fw.jobs.find(search_str)

    def get_job_by_id(self, job_id: str) -> Optional[Job]:
        """Find the Job with matching ID.

        Args:
            job_id: Flywheel job id

        Returns:
            Job: Flywheel Job object if found, else None
        """
        try:
            return self.__fw.get_job(job_id)
        except ApiException as error:
            log.warning(error)
            return None

    def get_matching_acquisition_files_info(
        self,
        *,
        container_id: str,
        dv_title: str,
        columns: List[str],
        filename_pattern: Optional[str] = "*.json",
        filters: Optional[str] = None,
        missing_data_strategy: Literal["drop-row", "none"] = "drop-row",
    ) -> Optional[List[Dict[str, str]]]:
        """Retrieve info on the list of files matching with the given filters
        (if any) from the specified Flywheel container.

        Args:
            container_id: Flywheel container ID
            dv_title: dataview title
            columns: list of columns to be included in dataview
            filename_pattern (optional): the filename pattern to match, default '*.json'
            filters (optional): If specified, returns visits matching with the filter
            missing_data_strategy: missing_data_strategy, default 'drop-row'

        Returns:
            List[Dict]: List of visits matching with the specified filters
        """

        builder = ViewBuilder(
            label=dv_title,
            columns=columns,
            container="acquisition",
            filename=filename_pattern,
            match="all",
            process_files=False,
            filter=filters,
            include_ids=False,
            include_labels=False,
        )
        builder = builder.missing_data_strategy(missing_data_strategy)
        view = builder.build()

        with self.read_view_data(view, container_id) as resp:
            try:
                result = json.load(resp)
            except JSONDecodeError as error:
                log.error(
                    "Error in loading dataview %s on container %s - %s",
                    view.label,
                    container_id,
                    error,
                )
                return None

        if not result or "data" not in result:
            return None

        return result["data"]

    def read_view_data(self, view: DataView, container_id: str) -> StreamReader:
        return self.__fw.read_view_data(view, container_id)

    def lookup(self, path):
        """Perform a path based lookup of a single node in the Flywheel
        hierarchy.

        Args:
            path: The path to resolve

        Returns:
            ResolverOutput
        """
        return self.__fw.lookup(path)

    def get_container_by_id(self, container_id: str) -> ContainerOutput:
        """Find the Flywheel container for the specified ID.

        Args:
            container_id: ID to lookup the container

        Returns:
            ContainerOutput: Container object
        """
        return self.__fw.get(container_id)

    def find_projects_with_pattern(self, pattern: str) -> List[flywheel.Project]:
        return self.__fw.projects.find(f"label=~{pattern}")

    def get_subject_by_label(self, label: str) -> list[Subject]:
        return self.__fw.subjects.find(f"label={label}")


def get_name(container) -> str:
    """Returns the name for the container.

    Args:
        container: the container
    Returns:
        ID for a group, name for a file, and label for everything else
    """
    if container.container_type == "file":
        return container.name
    if container.container_type == "group":
        return container.id

    return container.label


class GroupAdaptor:
    """Defines an adaptor for a flywheel group."""

    def __init__(self, *, group: flywheel.Group, proxy: FlywheelProxy) -> None:
        self._group = group
        self._fw = proxy

    @property
    def group(self) -> flywheel.Group:
        """Returns the enclosed group."""
        return self._group

    @property
    def id(self) -> str:
        """Return the ID for the group."""
        return self._group.id

    @property
    def label(self) -> str:
        """Return the label of the group."""
        return self._group.label

    def proxy(self) -> FlywheelProxy:
        """Return the proxy for the flywheel instance."""
        return self._fw

    def projects(self) -> List[flywheel.Project]:
        """Return projects for the group."""
        return list(self._group.projects.iter())

    def get_tags(self) -> List[str]:
        """Return the list of tags for the group.

        Returns:
          list of tags for the group
        """
        return self._group.tags

    def add_tag(self, tag: str) -> None:
        """Adds the tag to the group for the center.

        Args:
          tag: the tag to add
        """
        if tag in self._group.tags:
            return

        self._group.add_tag(tag)

    def add_tags(self, tags: Iterable[str]) -> None:
        """Adds the tags to the group.

        Args:
          tags: iterable collection of tags
        """
        for tag in tags:
            self.add_tag(tag)

    def get_group_users(self, *, access: Optional[str] = None) -> List[flywheel.User]:
        """Gets the users for the named group.

        Returns an empty list if the group does not exist or there are no
        user roles.
        If a role is specified, only the users with the role will be returned.

        Args:
          group_name: the group ID
          role: (optional) the role id
        Returns:
          the list of users for the group
        """
        permissions = self._group.permissions
        if not permissions:
            return []

        if access:
            permissions = [
                permission for permission in permissions if access == permission.access
            ]

        user_ids = [permission.id for permission in permissions if permission.id]
        users = []
        for user_id in user_ids:
            user = self._fw.find_user(user_id)
            if user:
                users.append(user)
        return users

    def get_user_access(self) -> List[AccessPermission]:
        """Returns the user access for the group.

        Returns:
          the access permissions for the group
        """
        return self._group.permissions

    def add_user_access(self, new_permission: AccessPermission) -> None:
        """Adds permission for user to access the group.

        Args:
          permission: permission object indicating user and group access
        """
        if not new_permission.id:
            log.error(
                "new permission has no user ID to add to group %s", self._group.label
            )
            return

        if not new_permission.access:
            log.warning(
                "new permission for user %s has no access, skipping", new_permission.id
            )
            return

        if self._fw.dry_run:
            log.info(
                "Dry Run: would add access %s for user %s to group %s",
                new_permission.access,
                new_permission.id,
                self._group.label,
            )
            return

        existing_permissions = [
            perm for perm in self._group.permissions if perm.id == new_permission.id
        ]
        if not existing_permissions:
            self._group.add_permission(new_permission)
            return

        self._group.update_permission(
            new_permission.id, AccessPermission(id=None, access=new_permission.access)
        )

    def add_permissions(self, permissions: List[AccessPermission]) -> None:
        """Adds the user access permissions to the group.

        Args:
          permissions: the list of access permissions
        """
        for permission in permissions:
            self.add_user_access(permission)

    def add_role(self, new_role: GroupRole) -> None:
        """Add the role to the the group for center.

        Args:
          new_role: the role to add
        """
        if not self._fw:
            log.error(
                "no Flywheel proxy given when adding users to group %s",
                self._group.label,
            )
            return

        self._fw.add_group_role(group=self._group, role=new_role)

    def add_roles(self, roles: Sequence[GroupRole]) -> None:
        """Adds the roles in the list to the group.

        Allows roles to be assigned to users for projects w/in the group.

        Args:
          roles: the list of roles
        """
        for role in roles:
            self.add_role(role)

    def get_project(
        self, label: str, info_update: Optional[dict[str, Any]] = None
    ) -> Optional["ProjectAdaptor"]:
        """Returns a project in this group with the given label.

        Creates a new project if none exists.

        Args:
          label: the label for the project
        Returns:
          the project in this group with the label
        """
        project = self._fw.get_project(group=self._group, project_label=label)
        if not project:
            return None

        adaptor = ProjectAdaptor(project=project, proxy=self._fw)
        adaptor.add_tags(self.get_tags())
        if info_update:
            adaptor.update_info(info_update)
        adaptor.add_admin_users(self.get_user_access())
        return adaptor

    def get_project_by_id(self, project_id: str) -> Optional["ProjectAdaptor"]:
        """Returns a project in this group with the given ID.

        Args:
          project_id: the ID for the project
        Returns:
          the project in this group with the ID
        """
        project = self._fw.get_project_by_id(project_id)
        if not project:
            log.warning("No project found with ID %s", project_id)
            return None

        return ProjectAdaptor(project=project, proxy=self._fw)

    def find_project(self, label: str) -> Optional["ProjectAdaptor"]:
        """Returns the project adaptor in the group with the label.

        Args:
          label: the label of the desired project
        Returns:
          Project adaptor for project with label if exists, None otherwise.
        """
        projects = self._fw.find_projects(group_id=self._group.id, project_label=label)
        if not projects:
            return None

        return ProjectAdaptor(project=projects[0], proxy=self._fw)


class ProjectError(Exception):
    """Exception class for errors involving projects."""


class ProjectAdaptor:
    """Defines an adaptor for a flywheel project."""

    def __init__(self, *, project: flywheel.Project, proxy: FlywheelProxy) -> None:
        self._project = project.reload()
        self._fw = proxy

    @classmethod
    def create(
        cls, proxy: FlywheelProxy, group_id: str, project_label: str
    ) -> "ProjectAdaptor":
        """Creates a project adaptor for the project.

        Args:
          proxy: the Flywheel proxy
          group_id: the group ID
          project_label: the label for the project
        Returns:
          the adaptor for the named project if one exists
        Raises:
          ProjectError if no project exists
        """
        projects = proxy.find_projects(group_id=group_id, project_label=project_label)
        if not projects:
            raise ProjectError(f"Could not find project {group_id}/{project_label}")

        return ProjectAdaptor(project=projects[0], proxy=proxy)

    def __pull_project(self) -> None:
        """Pulls the referenced project from Flywheel instance."""
        projects = self._fw.find_projects(group_id=self.group, project_label=self.label)
        if not projects:
            return

        self._project = projects[0]

    @property
    def proxy(self) -> FlywheelProxy:
        """Returns the flywheel proxy object."""
        return self._fw

    @property
    def project(self) -> flywheel.Project:
        """Returns the enclosed Project."""
        return self._project

    @property
    def id(self):
        """Returns the ID of the enclosed project."""
        return self._project.id

    @property
    def label(self):
        """Returns the label of the enclosed project."""
        return self._project.label

    @property
    def group(self) -> str:
        """Returns the group label of the enclosed project."""
        return self._project.group

    def get_pipeline_adcid(self) -> int:
        """Returns the pipeline ADCID for this project.

        If not in the project metadata, the ADCID from the metadata is returned.
        If neither is present raises an exception.

        Returns:
          the pipeline ADCID
        Raises:
          ProjectError if neither "pipeline_adcid" or "adcid" are set in
          project metadata.
        """

        pipeline_adcid = self._project.info.get("pipeline_adcid")
        if pipeline_adcid is not None:
            return pipeline_adcid

        adcid = self._project.info.get("adcid")
        if adcid is not None:
            return adcid

        raise ProjectError(f"Project {self.group}/{self.label} has no ADCID")

    def add_tag(self, tag: str) -> None:
        """Add tag to the enclosed project.

        Args:
          tag: the tag
        """
        if tag not in self._project.tags:
            self._project.add_tag(tag)

    def add_tags(self, tags: Iterable[str]) -> None:
        """Adds given tags to the enclosed project.

        Args:
          tags: iterable collection of tags
        """
        for tag in tags:
            self.add_tag(tag)

    def set_copyable(self, state: bool) -> None:
        """Sets the copyable state of the project to the value.

        Args:
          state: the copyable state to set
        """
        self._project.update(copyable=state)

    def set_description(self, description: str) -> None:
        """Sets the description of the project.

        Args:
          description: the project description
        """
        self._project.update(description=description)

    @property
    def files(self) -> List[FileEntry]:
        """The list of files associated with this project."""
        return self._project.files

    def get_file(self, name: str) -> Optional[FileEntry]:
        """Gets the file from the enclosed project.

        Args:
          name: the file name
        Returns:
          the named file
        """
        return self._project.get_file(name)

    def get_file_by_id(self, file_id: str) -> Optional[FileEntry]:
        """Returns the file by id.

        Args:
          file_id: the file ID
        Returns:
          the file with the file ID
        """
        # TODO: should return None if not in this project
        return self.proxy.get_file(file_id)

    def get_matching_files(self, query: str) -> List[FileEntry]:
        """Returns the files in this project matching the query.

        Use "parent_ref.type=project" for project files, and
        use "parent_ref.type=acquisition" for acquisition files.
        Otherwise, use FileEntry attributes to refine the list.

        Args:
          query: a finder query
        Returns:
          the list of files under this project matching the query
        """
        parent_query = f"parents.project={self.id}"
        finder_query = f"{parent_query},{query}" if query else parent_query

        return self.proxy.get_files(finder_query)

    def reload(self) -> Self:
        """Forces a reload on the project."""
        self._project = self._project.reload()

        return self

    def read_file(self, name: str) -> bytes:
        """Reads file from the named file.

        Args:
          name: the file name
        Returns:
          the bytes from the file
        """
        return self._project.read_file(name)

    @api_retry
    def upload_file(self, file_spec: flywheel.FileSpec) -> None:
        """Uploads the indicated file to enclosed project.

        Args:
          file_spec: the file specification
        """
        self._project.upload_file(file_spec)

    def upload_file_contents(
        self, *, filename: str, contents: str, content_type: str = "text"
    ) -> Optional[FileEntry]:
        """Uploads a file to the project using filename and string contents.

        Args:
            filename: the file name
            contents: the string contents of the file
            content_type: the MIME content type (defaults to "text")

        Returns:
            the FileEntry for the uploaded file, or None if upload failed
        """
        file_spec = flywheel.FileSpec(
            name=filename,
            contents=contents,
            content_type=content_type,
            size=len(contents),
        )
        try:
            self.upload_file(file_spec)
            self.reload()
            return self.get_file(filename)
        except ApiException as error:
            log.error(
                f"Failed to upload file {filename} to "
                f"{self.group}/{self.label}: {error}"
            )
            return None

    def get_user_roles(self, user_id: str) -> List[str]:
        """Gets the list of user role ids in this project.

        Args:
          user_id: the user id for the user
        Returns:
          list of role ids
        """
        assignments = [
            assignment
            for assignment in self._project.permissions
            if assignment.id == user_id
        ]
        if not assignments:
            return []

        return assignments[0].role_ids

    def add_user_role(self, user: User, role: RoleOutput) -> bool:
        """Adds the role to the user in the project.

        Args:
          user_id: the user id
          role_id: the role id
        """
        return self.add_user_roles(user=user, roles=[role])

    def add_user_roles(self, user: User, roles: Iterable[RoleOutput]) -> bool:
        """Adds the roles to the user in the project.

        Args:
          user: the user
          roles: the list of roles
        """
        if not roles:
            log.warning(
                "No roles to add to user %s in project %s/%s",
                user.id,
                self._project.group,
                self._project.label,
            )
            return False

        role_ids = [role.id for role in roles]
        return self.add_user_role_assignments(
            RolesRoleAssignment(id=user.id, role_ids=role_ids)
        )

    def add_user_role_assignments(self, role_assignment: RolesRoleAssignment) -> bool:
        """Adds role assignment to the project.

        Args:
          role_assignment: the role assignment
        Returns:
          True if role is set, False otherwise
        """
        user_roles = self.get_user_roles(role_assignment.id)
        if not user_roles:
            log_message = (
                f"User {role_assignment.id}"
                " has no permissions for "
                f"project {self._project.label}"
                ", adding roles"
            )
            if self._fw.dry_run:
                log.info("Dry Run: %s", log_message)
                return True

            log.info(log_message)
            user_role = RolesRoleAssignment(
                id=role_assignment.id, role_ids=role_assignment.role_ids
            )
            try:
                self._project.add_permission(user_role)
            except ApiException as error:
                raise ProjectError(
                    f"Failed to add user role to project: {error}"
                ) from error
            self.__pull_project()
            return True

        different = False
        for role_id in role_assignment.role_ids:
            if role_id not in user_roles:
                different = True
                user_roles.append(role_id)
        if not different:
            return True

        log_message = f"Adding roles to user {role_assignment.id}"
        if self._fw.dry_run:
            log.info("Dry Run: %s", log_message)
            return True
        try:
            self._project.update_permission(
                role_assignment.id, RolesRoleAssignment(id=None, role_ids=user_roles)
            )
        except ApiException as error:
            raise ProjectError(
                f"Failed to add user role to project: {error}"
            ) from error

        self.__pull_project()
        return True

    def add_admin_users(self, permissions: List[AccessPermission]) -> None:
        """Adds the users with admin access in the given group permissions.

        Args:
          permissions: the group access permissions
        """
        admin_role = self._fw.get_admin_role()
        assert admin_role
        admin_users = [
            permission.id for permission in permissions if permission.access == "admin"
        ]
        for user_id in admin_users:
            self.add_user_role_assignments(
                RolesRoleAssignment(id=user_id, role_ids=[admin_role.id])
            )

    def get_gear_rules(self) -> List[GearRule]:
        """Gets the gear rules for this project.

        Returns:
          the list of gear rules
        """
        return self._fw.get_project_gear_rules(project=self._project)

    def add_gear_rule(self, *, rule_input: GearRuleInput) -> None:
        """Adds the gear rule to the Flywheel project.

        Replaces an existing rule with the same name.

        Args:
          rule_input: the GearRuleInput for the gear
        """
        project_rules = self._fw.get_project_gear_rules(self._project)
        conflict = None
        for rule in project_rules:
            if rule.name == rule_input.name:
                conflict = rule
                break

        if self._fw.dry_run:
            if conflict:
                log.info(
                    "Dry Run: would remove conflicting rule %s from project %s",
                    conflict.name,
                    self._project.label,
                )
            log.info(
                "Dry Run: would add gear rule %s to project %s",
                rule_input.name,
                self._project.label,
            )
            return

        if conflict:
            self._fw.remove_project_gear_rule(project=self._project, rule=conflict)

        self._fw.add_project_rule(project=self._project, rule_input=rule_input)

    def remove_gear_rule(self, *, rule: GearRule) -> None:
        """Removes the gear rule from the project.

        Args:
          rule: the rule to remove
        """
        self._fw.remove_project_gear_rule(project=self._project, rule=rule)

    def get_apps(self) -> List[AttrDict]:
        """Returns the list of viewer apps for the project.

        Returns:
          the viewer apps for the project
        """
        return self._fw.get_project_apps(self._project)

    def set_apps(self, apps: List[AttrDict]) -> None:
        """Sets the viewer apps for the project.

        Args:
          apps: the list of viewer apps to add
        """
        self._fw.set_project_apps(project=self._project, apps=apps)

    def get_dataviews(self) -> List[DataView]:
        """Returns the list of dataviews for the project.

        Returns:
          the dataviews in the enclosed project
        """
        return self._fw.get_dataviews(self._project)

    def get_dataview(self, label: str) -> Optional[DataView]:
        """Returns the dataview in the project with the label.

        Args:
          label: the label for the desired dataview
        Returns:
          the dataview with matching label, None otherwise
        """
        dataviews = self.get_dataviews()
        for dataview in dataviews:
            if label == dataview.label:
                return dataview

        return None

    def add_dataview(self, dataview: DataView) -> str:
        """Adds the dataview to the enclosed project.

        Args:
          dataview: the DataView to add
        """

        # Copy the dataview into a ContainerIdViewInput
        # which is required to add the dataview
        # copying all of the properties but "origin"
        view_template = ContainerIdViewInput(
            parent=dataview.parent,
            label=dataview.label,
            description=dataview.description,
            columns=dataview.columns,
            group_by=dataview.group_by,
            filter=dataview.filter,
            file_spec=dataview.file_spec,
            include_ids=dataview.include_ids,
            include_labels=dataview.include_labels,
            error_column=dataview.error_column,
            missing_data_strategy=dataview.missing_data_strategy,
            sort=dataview.sort,
            id=dataview.id,
        )
        view_id = self._fw.add_dataview(project=self._project, viewinput=view_template)
        return view_id.id

    def read_dataview(self, view: DataView) -> StreamReader:
        return self._fw.read_view_data(view, self._project.id)

    def get_info(self) -> Dict[str, Any]:
        """Returns the info object for this project.

        Returns:
          the dictionary object with info for project
        """
        self._project = self._project.reload()
        return self._project.info

    def update_info(self, info: Dict[str, Any]) -> None:
        """Updates the info object for this project.

        Args:
          info: the info object
        """
        log.info("updating info for project %s", self._project.label)
        self._project.update_info(info)

    def get_custom_project_info(self, key_path: str) -> Optional[Any | Dict[str, Any]]:
        """Retrieve custom project info metadata value by key path.

        Args:
            key_path: path to desired field (level1_key:level2_key:....:key)

        Returns:
            Any: metadata value if exists
        """

        keys = key_path.split(":")
        index = 0
        info: Dict[str, Any] | Any = self.get_info()
        while index < len(keys) and info:
            info = info.get(keys[index])
            index += 1

        return info

    def add_subject(self, label: str) -> SubjectAdaptor:
        """Adds a subject with the given label.

        Args:
          label: the subject label
        Returns:
          the created Subject object
        """
        return SubjectAdaptor(self._project.add_subject(label=label))

    def find_subject(self, label: str) -> Optional[SubjectAdaptor]:
        """Finds the subject with the label.

        Args:
          label: the subject label
        Returns:
          the Subject object with the label. None, otherwise
        """
        subject = self._project.subjects.find_first(f"label={label}")
        if subject:
            return SubjectAdaptor(subject)

        return None

    def get_subject_by_id(self, subject_id: str) -> Optional[SubjectAdaptor]:
        """Gets the subject with the given id.

        Args:
          subject_id: the subject ID
        Returns:
          the Subject object the ID if found. None, otherwise
        """
        subject = self._project.subjects.find_first(f"_id={subject_id}")
        if subject:
            return SubjectAdaptor(subject)

        return None
