"""Run method for user management."""
import logging
from collections import defaultdict
from typing import List

import flywheel
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from redcap.nacc_directory import UserDirectoryEntry

log = logging.getLogger(__name__)


def run(*, proxy: FlywheelProxy, user_list, admin_users: List[flywheel.User]):
    """does the work."""

    # ignore administrative users in directory
    admin_map = {user.id: user for user in admin_users}

    # gather users by center
    center_prefix = 'adcid-'
    center_map = defaultdict(list)
    for user_doc in user_list:
        user_entry = UserDirectoryEntry.create(user_doc)
        if user_entry.credentials['id'] in admin_map:
            log.info('Skipping admin user: %s', user_entry.credentials['id'])
            continue
        center_map[f"{center_prefix}{user_entry.center_id}"].append(user_entry)

    for center_tag, center_users in center_map.items():
        group_list = proxy.find_groups_by_tag(center_tag)
        if len(group_list) > 1:
            log.error('Error: expecting only one center for tag %s',
                      center_tag)
            continue
        center_group = group_list[0]

        for project in center_group.projects():
            pass
