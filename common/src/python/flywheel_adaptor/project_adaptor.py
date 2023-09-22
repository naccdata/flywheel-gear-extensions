"""Defines adaptor class for flywheel.Project."""

import logging
from typing import List, Optional

import flywheel
from flywheel import (AccessPermission, ContainerIdViewInput, DataView,
                      GearRule, GearRuleInput, RolesRoleAssignment, ViewerApp)
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

    @property
    def group(self) -> str:
        """Returns the group label of the enclosed project."""
        return self.__project.group

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

        self.__project.update_permission(
            role_assignment.id,
            RolesRoleAssignment(id=None, role_ids=user_roles))

    def add_admin_users(self, permissions: List[AccessPermission]) -> None:
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

    def get_apps(self) -> List[ViewerApp]:
        """Returns the list of viewer apps for the project.

        Returns:
          the viewer apps for the project
        """
        return self.__fw.get_project_apps(self.__project)

    def set_apps(self, apps: List[ViewerApp]) -> None:
        """Sets the viewer apps for the project.

        Args:
          apps: the list of viewer apps to add
        """
        self.__fw.set_project_apps(project=self.__project, apps=apps)

    def get_dataviews(self) -> List[DataView]:
        """Returns the list of dataviews for the project.

        Returns:
          the dataviews in the enclosed project
        """
        return self.__fw.get_dataviews(self.__project)

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
            id=dataview.id)
        view_id = self.__fw.add_dataview(project=self.__project,
                                         viewinput=view_template)
        return view_id.id
