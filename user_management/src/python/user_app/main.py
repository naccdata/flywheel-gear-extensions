"""Run method for user management."""
import logging
from collections import defaultdict
from typing import Dict, List, Set

from flywheel import RolesRoleAssignment, User
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor
from redcap.nacc_directory import UserDirectoryEntry

log = logging.getLogger(__name__)


def create_user(proxy: FlywheelProxy, user_entry: UserDirectoryEntry) -> User:
    """Creates a user object from the directory entry.

    Flywheel constraint (true as of version 17): the user ID and email must be
    the same even if ID is an ePPN in add_user
    
    Case can be an issue for IDs both with ORCID and ePPNs.
    Best we can do is assume ID from directory is correct.

    Args:
      proxy: the proxy object for the FW instance
      user_entry: the directory entry for the user
    Returns:
      the ID for flywheel User created from the directory entry
    """
    user_id = user_entry.credentials['id']
    new_id = proxy.add_user(
        User(id=user_id,
             firstname=user_entry.name['first_name'],
             lastname=user_entry.name['last_name'],
             email=user_id))
    user = proxy.find_user(new_id)
    assert user, f"Failed to find user {new_id} that was just created"
    return user


def create_user_map(
        user_list, skip_list: Set[str]) -> Dict[str, List[UserDirectoryEntry]]:
    """Creates a map from center tags to lists of nacc directory entries.

    Args:
      user_list: the list of user objects from directory yaml file
      skip_list: the list of user IDs to skip
    Returns:
      map from center tags to lists of nacc directory entries
    """
    center_prefix = 'adcid-'
    center_map = defaultdict(list)
    for user_doc in user_list:
        user_entry = UserDirectoryEntry.create(user_doc)
        if user_entry.credentials['id'] in skip_list:
            log.info('Skipping user: %s', user_entry.credentials['id'])
            continue

        center_map[f"{center_prefix}{user_entry.center_id}"].append(user_entry)

    return center_map


def update_email(*, proxy: FlywheelProxy, user: User, email: str) -> None:
    """Updates user email on FW instance if email is different.

    Checks whether user email is the same as new email.

    Note: this needs to be applied after a user is created if the ID and email
    are different, because the API wont allow a creating new user with ID and 
    email different.

    Args:
      proxy: Flywheel proxy object
      user: local user object
      email: email address to set
    """
    if user.email == email:
        return

    log.info('Setting user %s email to %s', user.id, email)
    proxy.set_user_email(user=user, email=email)


# pylint: disable=(too-many-locals)
def run(*, proxy: FlywheelProxy, user_list, skip_list: Set[str]):
    """Manages users based on user list."""

    # gather users by center
    center_map = create_user_map(user_list=user_list, skip_list=skip_list)

    roles_map = proxy.get_roles()
    read_only_role = roles_map.get('read-only')
    if not read_only_role:
        log.error('Could not find read-only role, cannot add permissions')
        return

    for center_tag, center_users in center_map.items():
        group_list = proxy.find_groups_by_tag(f"^{center_tag}$")
        if len(group_list) > 1:
            log.error('Error: expecting only one center for tag %s',
                      center_tag)
            continue
        center_group = GroupAdaptor(group=group_list[0], proxy=proxy)

        # for now, just giving all users read-only access to 'ingest-scan'
        project_label = 'ingest-scan'
        project = center_group.find_project(project_label)
        if not project:
            log.warning('center %s does not have project %s',
                        center_group.label, project_label)
            continue

        for user_entry in center_users:
            user = proxy.find_user(user_entry.credentials['id'])
            if not user:
                user = create_user(proxy=proxy, user_entry=user_entry)
                log.info('Added user %s', user.id)
            update_email(proxy=proxy, user=user, email=user_entry.email)

            added = project.add_user_roles(
                RolesRoleAssignment(id=user.id, role_ids=[read_only_role.id]))
            if added:
                log.info('Granted %s permission to user %s in project %s/%s',
                         read_only_role.label, user.id, center_group.label,
                         project.label)
