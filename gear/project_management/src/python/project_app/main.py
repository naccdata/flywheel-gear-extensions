"""Defines project management computation."""

import logging
from typing import List, Optional

from authorization.client import AuthorizationClient
from centers.nacc_group import NACCGroup
from flywheel.models.group_role import GroupRole
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from projects.hierarchy_seeder import ResourceHierarchySeeder
from projects.study import StudyModel
from projects.study_mapping import StudyMappingVisitor

log = logging.getLogger(__name__)


def get_project_roles(flywheel_proxy, role_names: List[str]) -> List[GroupRole]:
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
            log.warning("no such role %s", name)
    return role_list


def run(
    *,
    proxy: FlywheelProxy,
    admin_group: NACCGroup,
    study_list: List[StudyModel],
    authorization_client: Optional[AuthorizationClient] = None,
):
    """Runs project pipeline creation/management.

    Args:
      proxy: the proxy for the Flywheel instance
      admin_group: the administrative group
      study_list: the list of input study objects
      authorization_client: optional authorization client for hierarchy seeding
    """
    if authorization_client is None:
        log.warning("Authorization hierarchy seeding is disabled (no client available)")
        seeder = None
    else:
        seeder = ResourceHierarchySeeder(client=authorization_client)

    visitor = StudyMappingVisitor(
        flywheel_proxy=proxy,
        admin_permissions=admin_group.get_user_access(),
        hierarchy_seeder=seeder,
    )
    for study in study_list:
        visitor.visit_study(study)

    if seeder and seeder.failure_count > 0:
        log.warning(
            "Authorization hierarchy seeding completed with %d failure(s)",
            seeder.failure_count,
        )
