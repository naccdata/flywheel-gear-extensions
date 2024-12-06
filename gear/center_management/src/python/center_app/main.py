"""Defines center management computation."""

import logging
from typing import List

from centers.center_group import CenterGroup
from centers.center_info import CenterInfo
from centers.nacc_group import NACCGroup
from flywheel.models.group_role import GroupRole
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy

log = logging.getLogger(__name__)


def get_project_roles(flywheel_proxy,
                      role_names: List[str]) -> List[GroupRole]:
    """Get the named roles.

    Returns all roles matching a name in the list.
    Logs a warning if a name is not matched.

    Args:
      role_names: the role names
    Returns:
      the list of roles with the names
    """
    role_list = []
    for name in role_names:
        role = flywheel_proxy.get_role(name)
        if role:
            role_list.append(GroupRole(id=role.id))
        else:
            log.warning('no such role %s', name)
    return role_list


def run(*,
        proxy: FlywheelProxy,
        admin_group: NACCGroup,
        center_list: List[CenterInfo],
        role_names: List[str],
        new_only: bool = False):
    """Runs center creation/management.

    Args:
      proxy: the proxy for the Flywheel instance
      admin_group: the administrative group
      center_list: the list of center objects
      role_names: list of project role names
      new_only: whether to only create centers with new tag
    """
    center_roles = get_project_roles(proxy, role_names)

    for center in center_list:
        if new_only and 'new-center' not in center.tags:
            log.info(f"new_only set to True and {center.name} does not " +
                     "have `new-center` tag, skipping")
            continue

        try:
            center_group = CenterGroup.create_from_center(center=center,
                                                          proxy=proxy)
        except FlywheelError as error:
            log.warning("Unable to create center: %s", str(error))
            continue

        center_group.add_roles(center_roles)
        admin_group.add_center(center_group)

        admin_access = admin_group.get_user_access()
        if admin_access:
            center_group.add_permissions(admin_access)
            center_group.add_center_portal()
