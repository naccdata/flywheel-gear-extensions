"""Defines project creation functions for calls to Flywheel."""
import logging
from typing import List, Mapping, Optional, Union

import flywheel  # type: ignore
from flywheel.models.gear_rule_input import GearRuleInput
from flywheel.models.roles_role import RolesRole
from flywheel.models.roles_role_assignment import RolesRoleAssignment

log = logging.getLogger(__name__)


class FlywheelProxy:
    """Defines a proxy object for group and project creation on a Flywheel
    instance."""

    def __init__(self, api_key: str, dry_run: bool = True) -> None:
        """Initializes a flywheel proxy object.

        Args:
          api_key: the API key
          dry_run: whether proxy will be used for a dry run
        """
        self.__fw = flywheel.Client(api_key)
        self.__dry_run = dry_run
        self.__roles: Optional[Mapping[str, RolesRoleAssignment]] = None
        self.__admin_role = None

    @property
    def dry_run(self):
        """Indicates whether proxy is set for a dry run.

        Returns:
            True if proxy is set for a dry run. False otherwise.
        """
        return self.__dry_run

    def find_projects(self, *, group_id: str,
                      project_label: str) -> List[flywheel.Project]:
        """Finds a flywheel project with a given label, within a group ID if
        specified. Otherwise it's site wide.

        Args:
            project_label: the project label to search for
            group_id: the group ID the project may be in

        Returns:
            existing: a list of all matching projects.
        """
        return self.__fw.projects.find(
            f"parents.group={group_id},label={project_label}")  # type: ignore

    def find_groups(self, group_id: str) -> List[flywheel.Group]:
        """Searches for and returns a group if it exists.

        Args:
            group_id: the ID to search for

        Returns:
            group: the group (or empty list if not found)
        """
        return self.__fw.groups.find(f'_id={group_id}')  # type: ignore

    def find_users(self, user_id: str) -> List[flywheel.User]:
        """Searches for and returns a user if it exists.

        Args:
            user_id: the ID to search for

        Returns:
            the user, or an empty list if now found
        """
        return self.__fw.users.find(f'_id={user_id}')  # type: ignore

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
        """
        group = self.find_groups(group_id)
        if group:
            return group[0]

        if self.__dry_run:
            log.info('Dry Run: would create group %s', group_id)
            return flywheel.Group(label=group_label, id=group_id)

        log.info('creating group...')
        # This just returns a string of the group ID
        group = self.__fw.add_group(flywheel.Group(group_id, group_label))
        # we must fw.get_group() with ID string to get the actual Group object.
        group = self.__fw.get_group(group)
        log.info("success")

        return group

    def get_project(self, *, group: flywheel.Group,
                    project_label: str) -> Optional[flywheel.Project]:
        """Given a flywheel project label and optional group ID, search for the
        project, and create it if it doesn't exist returns the project, found
        or created.

        Args:
            project_label: the project label to find or create
            group_id: the group id the project is in - required if creating

        Returns:
            project: the found or created project
        """
        group_id = group.id
        assert group_id
        existing_projects = self.find_projects(group_id=group_id,
                                               project_label=project_label)
        if existing_projects and len(existing_projects) == 1:
            project_ref = f"{group.id}/{project_label}"
            log.info('Project %s exists', project_ref)
            return existing_projects[0]

        if not group:
            log.error(('No project named %s and no group id provided.'
                       '  Please provide a group ID to create the project in'),
                      project_label)
            return None

        project_ref = f"{group.id}/{project_label}"
        if self.__dry_run:
            log.info('Dry Run: would create project %s', project_ref)
            return flywheel.Project(label=project_label,
                                    parents={'group': group.id})

        log.info('creating project...')
        project = group.add_project(label=project_label)
        log.info('success')

        return project

    def __get_roles(self) -> Mapping[str, RolesRoleAssignment]:
        """Gets all roles for the FW instance."""
        if not self.__roles:
            all_roles = self.__fw.get_all_roles()
            self.__roles = {role.label: role for role in all_roles}
        return self.__roles

    def get_admin_role(self) -> Optional[RolesRoleAssignment]:
        """Gets admin role."""
        if not self.__admin_role:
            role_map = self.__get_roles()
            self.__admin_role = role_map.get('admin')
        return self.__admin_role

    def add_project_permissions(self, *, project: flywheel.Project,
                                user: flywheel.User, role: RolesRole) -> None:
        """Adds the user with the role to the project.

        Note: project and group permissions in the FW SDK use different types.

        Args:
          project: the project
          user: the user to add
          role: the user role to add
        """
        if self.__dry_run:
            log.info("Dry Run: would add role %s to user %s for project %s",
                     user.id, role.label, project.label)
            return

        permissions = [
            permission for permission in project.permissions
            if permission.id == user.id
        ]
        if not permissions:
            log.info("User %s has no permissions for project %s, adding %s",
                     user.id, project.label, role.label)
            user_role = RolesRoleAssignment(id=user.id, role_ids=[role.id])
            project.add_permission(user_role)
            return

        permission = permissions[0]
        user_roles = permission.role_ids
        if role.id in user_roles:
            return
        user_roles.append(role.id)
        project.update_permission(user.id, {'role_ids': user_roles})

    def add_group_permissions(self, *, group: flywheel.Group,
                              user: flywheel.User, access: str) -> None:
        """Adds the user with the role to the group.

        Note: project and group permissions in the FW SDK use different types.

        Args:
          group: the group
          user: the user to add
          access: the user role to add ('admin','rw','ro')
        """
        if self.__dry_run:
            log.info('Dry Run: would add access %s for user %s to group %s',
                     access, user.id, group.label)
            return

        permissions = [
            permission for permission in group.permissions
            if permission.id == user.id
        ]
        if not permissions:
            group.add_permission({"access": access, "id": user.id})
            return

        group.update_permission(user.id, {"access": access})

    def add_admin_users(self, *, obj: Union[flywheel.Group, flywheel.Project],
                        users: List[flywheel.User]) -> None:
        """Adds the users with admin role to the given group or project.

        Args:
          obj: group or project
          users: list of users to be given admin role
        """
        admin_role = self.get_admin_role()
        assert admin_role

        if isinstance(obj, flywheel.Project):
            for user in users:
                self.add_project_permissions(project=obj,
                                             user=user,
                                             role=admin_role)
            return

        for user in users:
            self.add_group_permissions(group=obj, user=user, access='admin')

    def get_group_users(self,
                        group: flywheel.Group,
                        *,
                        role: Optional[str] = None) -> List[flywheel.User]:
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
        permissions = group.permissions
        if not permissions:
            return []

        if role:
            permissions = [
                permission for permission in permissions
                if role == permission.access
            ]

        user_ids = [permission.id for permission in permissions]
        users = []
        for user_id in user_ids:
            user = self.find_users(user_id)[0]
            if user:
                users.append(user)
        return users

    def get_project_gear_rules(
            self, project) -> List[flywheel.models.gear_rule.GearRule]:
        """Get the gear rules from the given project.

        Args:
          project: the flywheel project

        Returns:
          the gear rules
        """
        return self.__fw.get_project_rules(project.id)

    def add_project_gear_rule(self, *, project: flywheel.Project,
                              rule_input: GearRuleInput) -> None:
        """Adds the gear rule to the Flywheel project.

        Replaces an existing rule with the same name.

        Args:
          project: the flywheel project
          rule_input: the GearRuleInput for the gear
        """
        project_rules = self.get_project_gear_rules(project)
        conflict = None
        for rule in project_rules:
            if rule.name == rule_input.name:
                conflict = rule
                break

        if self.__dry_run:
            if conflict:
                log.info(
                    'Dry Run: would remove conflicting '
                    'rule %s from project %s', conflict.name, project.label)
            log.info('Dry Run: would add gear rule %s to project %s',
                     rule_input.name, project.label)
            return

        if conflict:
            self.__fw.remove_project_rule(project.id, conflict.id)

        self.__fw.add_project_rule(project.id, rule_input)
