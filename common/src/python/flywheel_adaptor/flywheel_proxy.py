"""Defines project creation functions for calls to Flywheel."""
import logging
from typing import List, Mapping, Optional

import flywheel  # type: ignore
from flywheel.models.gear_rule_input import GearRuleInput
from flywheel.models.roles_role import RolesRole

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
        self.__roles: Optional[Mapping[str, RolesRole]] = None
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
            the group (or empty list if not found)
        """
        return self.__fw.groups.find(f'_id={group_id}')  # type: ignore

    def find_groups_by_tag(self, tag_pattern: str) -> List[flywheel.Group]:
        """Searches for groups with tags matching the pattern.

        Args:
          tag_pattern: raw string regex pattern

        Returns:
          the list of groups
        """
        return self.__fw.groups.find(f"tags=~{tag_pattern}")  # type: ignore

    def find_users(self, user_id: str) -> List[flywheel.User]:
        """Searches for and returns a user if it exists.

        Args:
            user_id: the ID to search for

        Returns:
            a list with the user, or an empty list if not found
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

    def __get_roles(self) -> Mapping[str, RolesRole]:
        """Gets all roles for the FW instance."""
        if not self.__roles:
            all_roles = self.__fw.get_all_roles()
            self.__roles = {role.label: role for role in all_roles}
        return self.__roles

    def get_role(self, label) -> Optional[RolesRole]:
        """Gets role with label.

        Args:
          label: the name of the role
        Returns:
          the role with the name if one exists. None, otherwise
        """
        role_map = self.__get_roles()
        return role_map.get(label)

    def get_admin_role(self) -> Optional[RolesRole]:
        """Gets admin role."""
        if not self.__admin_role:
            self.__admin_role = self.get_role('admin')
        return self.__admin_role

    def add_group_role(self, *, group: flywheel.Group,
                       role: RolesRole) -> None:
        """Add role to the group.

        Args:
          group: the group
          role: the role
        """
        if role.id in group.roles:
            return

        if self.dry_run:
            log.info("Dry run: would add role %s to group %s", role.name,
                     group.label)
            return

        self.__fw.add_role_to_group(group.id, role)

    def get_project_gear_rules(
            self, project) -> List[flywheel.models.gear_rule.GearRule]:
        """Get the gear rules from the given project.

        Args:
          project: the flywheel project

        Returns:
          the gear rules
        """
        return self.__fw.get_project_rules(project.id)

    def add_project_rule(self, *, project: flywheel.Project,
                         rule_input: GearRuleInput) -> None:
        """Forwards call to the FW client."""
        self.__fw.add_project_rule(project.id, rule_input)

    def remove_project_gear_rule(
            self, *, project: flywheel.Project,
            rule: flywheel.models.gear_rule.GearRule) -> None:
        """Removes the gear rule from the project.

        Args:
          project: the project
          rule: the gear rule
        """
        if self.dry_run:
            log.info('Dry run: would remove rule %s from project %s',
                     rule.name, project.label)
            return

        self.__fw.remove_project_rule(project.id, rule.id)
