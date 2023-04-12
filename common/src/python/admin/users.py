"""User admin functions."""

import logging
from typing import List

import flywheel
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.group_adaptor import GroupAdaptor  # type: ignore

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

    admin_group = GroupAdaptor(group=groups[0], proxy=flywheel_proxy)
    admin_users = admin_group.get_group_users(access='admin')
    return admin_users
