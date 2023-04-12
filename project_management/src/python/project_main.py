"""Defines project management computation."""

import logging
from typing import List

from flywheel.models.permission_access_permission import \
    PermissionAccessPermission
from flywheel.models.roles_role import RolesRole
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from projects.project import Project
from projects.project_mapping import ProjectMappingAdaptor

log = logging.getLogger(__name__)


def get_roles(flywheel_proxy, role_names: List[str]) -> List[RolesRole]:
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
            role_list.append(role)
        else:
            log.warning('no such role %s', name)
    return role_list


def run(*, proxy: FlywheelProxy, project_list,
        admin_access: List[PermissionAccessPermission], role_names: List[str]):
    """Runs project pipeline creation/management.

    Args:
      proxy: the proxy for the Flywheel instance
      project_list: the list of project input
      admin_users: the list of admin users
      template_map: map from datatype name to template projects
    """

    center_roles = get_roles(proxy, role_names)

    for project_doc in project_list:
        project = Project.create(project_doc)
        project_mapper = ProjectMappingAdaptor(project=project,
                                               flywheel_proxy=proxy,
                                               admin_access=admin_access,
                                               center_roles=center_roles)
        project_mapper.create_project_pipelines()
