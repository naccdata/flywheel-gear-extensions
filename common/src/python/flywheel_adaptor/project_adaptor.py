"""Defines adaptor class for flywheel.Project."""

import logging
from typing import List

import flywheel
from flywheel.models.gear_rule import GearRule
from flywheel.models.gear_rule_input import GearRuleInput
from flywheel.models.permission_access_permission import \
    PermissionAccessPermission
from flywheel.models.roles_role_assignment import RolesRoleAssignment
from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


class ProjectAdaptor:
    """Defines an adaptor for a flywheel project."""

    def __init__(self, *, project: flywheel.Project,
                 proxy: FlywheelProxy) -> None:
        self.__project = project
        self.__fw = proxy

    # pylint: disable=(invalid-name)
    @property
    def id(self):
        """Returns the ID of the enclosed project."""
        return self.__project.id

    @property
    def label(self):
        """Returns the label of the enclosed project."""
        return self.__project.label

    def add_tag(self, tag: str) -> None:
        """Add tag to the enclosed project.

        Args:
          tag: the tag
        """
        if tag not in self.__project.tags:
            self.__project.add_tag(tag)

    def set_description(self, description: str) -> None:
        """Sets the description of the project.

        Args:
          description: the project description
        """
        self.__project.update(description=description)

    def get_file(self, name: str):
        """Gets the file from the enclosed project.

        Args:
          name: the file name
        Returns:
          the named file
        """
        return self.__project.get_file(name)

    def upload_file(self, file_spec: flywheel.FileSpec) -> None:
        """Uploads the indicated file to enclosed project.

        Args:
          file_spec: the file specification
        """
        self.__project.upload_file(file_spec)

    def add_user_roles(self, role_assignment: RolesRoleAssignment) -> None:
        """Adds role assignment to the project.

        Args:
          role_assignment: the role assignment
        """
        if self.__fw.dry_run:
            log.info("Dry Run: would add role to user %s for project %s",
                     role_assignment.id, self.__project.label)
            return

        existing_assignments = [
            assignment for assignment in self.__project.permissions
            if assignment.id == role_assignment.id
        ]
        if not existing_assignments:
            log.info("User %s has no permissions for project %s, adding roles",
                     role_assignment.id, self.__project.label)
            user_role = RolesRoleAssignment(id=role_assignment.id,
                                            role_ids=role_assignment.role_ids)
            self.__project.add_permission(user_role)
            return

        assignment = existing_assignments[0]
        user_roles = assignment.role_ids
        for role_id in role_assignment.role_ids:
            if role_id not in user_roles:
                user_roles.append(role_id)
        self.__project.update_permission(role_assignment.id,
                                         {'role_ids': user_roles})

    def add_admin_users(self,
                        permissions: List[PermissionAccessPermission]) -> None:
        """Adds the users with admin access in the given group permissions.

        Args:
          permissions: the group access permissions
        """
        admin_role = self.__fw.get_admin_role()
        assert admin_role
        for permission in permissions:
            self.add_user_roles(
                RolesRoleAssignment(id=permission.id,
                                    role_ids=[admin_role.id]))

    def get_gear_rules(self) -> List[GearRule]:
        """Gets the gear rules for this project.

        Returns:
          the list of gear rules
        """
        return self.__fw.get_project_gear_rules(project=self.__project)

    def add_gear_rule(self, *, rule_input: GearRuleInput) -> None:
        """Adds the gear rule to the Flywheel project.

        Replaces an existing rule with the same name.

        Args:
          rule_input: the GearRuleInput for the gear
        """
        project_rules = self.__fw.get_project_gear_rules(self.__project)
        conflict = None
        for rule in project_rules:
            if rule.name == rule_input.name:
                conflict = rule
                break

        if self.__fw.dry_run:
            if conflict:
                log.info(
                    'Dry Run: would remove conflicting '
                    'rule %s from project %s', conflict.name,
                    self.__project.label)
            log.info('Dry Run: would add gear rule %s to project %s',
                     rule_input.name, self.__project.label)
            return

        if conflict:
            self.__fw.remove_project_gear_rule(project=self.__project,
                                               rule=conflict)

        self.__fw.add_project_rule(project=self.__project,
                                   rule_input=rule_input)

    def remove_gear_rule(self, *, rule: GearRule) -> None:
        """Removes the gear rule from the project.

        Args:
          rule: the rule to remove
        """
        self.__fw.remove_project_gear_rule(project=self.__project, rule=rule)
