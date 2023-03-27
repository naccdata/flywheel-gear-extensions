"""User admin functions."""

import logging
from typing import List

import flywheel  # type: ignore
from projects.flywheel_proxy import FlywheelProxy

log = logging.getLogger(__name__)


def get_admin_users(flywheel_proxy: FlywheelProxy,
                    group_name: str) -> List[flywheel.User]:
    """Returns the admin users for the group with the given name.

    Args:
      flywheel_proxy: proxy object for flywheel instance
      group_name: name of the group
    Returns:
      list of admin users of the group if any
    """
    if not group_name:
        return []

    groups = flywheel_proxy.find_groups(group_name)
    if not groups:
        log.warning("No group found with name %s", group_name)
        return []

    admin_group = groups[0]
    admin_users = flywheel_proxy.get_group_users(admin_group, role='admin')
    return admin_users
