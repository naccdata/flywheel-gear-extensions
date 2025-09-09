"""Defines center management computation."""

import logging
from typing import List

from centers.center_group import CenterGroup
from centers.center_info import CenterList
from centers.nacc_group import NACCGroup
from flywheel.models.group_role import GroupRole
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    admin_group: NACCGroup,
    center_list: CenterList,
    role_names: List[str],
    new_only: bool = False,
):
    """Runs center creation/management.

    The "center" list may include CenterInfo objects that represent a data
    pipeline. These are added to the center map in the admin group for
    book-keeping purposes.

    For a (non-pipeline) CenterInfo object:
    - a CenterGroup is created (creates a FW group)
    - user roles in the role names are added to the underlying group
    - the center is added to the admin group center map
    - the center-portal project is added to the center group

    Args:
      proxy: the proxy for the Flywheel instance
      admin_group: the administrative group
      center_map: map of CenterInfo objects to optional list of tags
      role_names: list of project role names
      new_only: whether to only create centers with new tag
    """
    center_roles = proxy.get_user_roles(role_names)

    for center in center_list:
        if center.is_pipeline():
            log.info("skipping pipeline ADCID %s", center.adcid)
            continue

        if new_only and center.tags and "new-center" not in center.tags:
            log.info(
                f"new_only set to True and {center.name} does not "
                + "have `new-center` tag, skipping"
            )
            continue

        try:
            tags = list(center.tags) if center.tags else None
            center_group = CenterGroup.create_from_center(
                center=center, tags=tags, proxy=proxy
            )
        except FlywheelError as error:
            log.warning("Unable to create center: %s", str(error))
            continue

        center_group.add_roles([GroupRole(id=role.id) for role in center_roles])
        admin_group.add_center(center_group)

        admin_access = admin_group.get_user_access()
        if admin_access:
            center_group.add_permissions(admin_access)
            center_group.add_center_portal()
