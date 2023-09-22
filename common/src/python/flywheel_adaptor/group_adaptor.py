"""Defines adaptor class for flywheel.Group."""

import logging
from typing import List, Optional

import flywheel
from flywheel import AccessPermission, RolesRole
from flywheel_adaptor.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


class GroupAdaptor:
    """Defines an adaptor for a flywheel group."""

    def __init__(self, *, group: flywheel.Group, proxy: FlywheelProxy) -> None:
        self.__group = group
        self.__fw = proxy

    @property
    def label(self) -> str:
        """Return the label of the group."""
        return self.__group.label

    def proxy(self) -> FlywheelProxy:
        """Return the proxy for the flywheel instance."""
        return self.__fw

    def projects(self) -> List[flywheel.Project]:
        """Return projects for the group."""
        return self.__group.projects()

    def get_tags(self) -> List[str]:
        """Return the list of tags for the group.

        Returns:
          list of tags for the group
        """
        return self.__group.tags

    def add_tag(self, tag: str) -> None:
        """Adds the tag to the group for the center.

        Args:
          tag: the tag to add
        """
        self.__group.add_tag(tag)

    def get_group_users(self,
                        *,
                        access: Optional[str] = None) -> List[flywheel.User]:
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
        permissions = self.__group.permissions
        if not permissions:
            return []

        if access:
            permissions = [
                permission for permission in permissions
                if access == permission.access
            ]

        user_ids = [
            permission.id for permission in permissions if permission.id
        ]
        users = []
        for user_id in user_ids:
            user = self.__fw.find_users(user_id)[0]
            if user:
                users.append(user)
        return users

    def get_user_access(self) -> List[AccessPermission]:
        """Returns the user access for the group.

        Returns:
          the access permissions for the group
        """
        return self.__group.permissions

    def add_user_access(self, new_permission: AccessPermission) -> None:
        """Adds permission for user to access the group of the center.

        Args:
          permission: permission object indicating user and group access
        """
        if not new_permission.id:
            log.error('new permission has no user ID to add to group %s',
                      self.__group.label)
            return

        if not new_permission.access:
            log.warning('new permission for user %s has no access, skipping',
                        new_permission.id)
            return

        if self.__fw.dry_run:
            log.info('Dry Run: would add access %s for user %s to group %s',
                     new_permission.access, new_permission.id,
                     self.__group.label)
            return

        existing_permissions = [
            perm for perm in self.__group.permissions
            if perm.id == new_permission.id
        ]
        if not existing_permissions:
            self.__group.add_permission(new_permission)
            return

        self.__group.update_permission(
            new_permission.id,
            AccessPermission(id=None, access=new_permission.access))

    def add_role(self, new_role: RolesRole) -> None:
        """Add the role to the the group for center.

        Args:
          new_role: the role to add
        """
        if not self.__fw:
            log.error('no Flywheel proxy given when adding users to group %s',
                      self.__group.label)
            return

        self.__fw.add_group_role(group=self.__group, role=new_role)

    def get_project(self, label: str) -> Optional[flywheel.Project]:
        """Returns a project in this group with the given label.

        Creates a new project if none exists.

        Args:
          label: the label for the project
        Returns:
          the project in this group with the label
        """
        return self.__fw.get_project(group=self.__group, project_label=label)
