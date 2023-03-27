"""Defines project management computation."""

import logging
from typing import Dict, List

import flywheel
from projects.flywheel_proxy import FlywheelProxy
from projects.project import Project
from projects.project_mapping import ProjectMappingAdaptor
from projects.template_project import TemplateProject

log = logging.getLogger(__name__)


def run(*, proxy: FlywheelProxy, project_list,
        admin_users: List[flywheel.User],
        template_map: Dict[str, Dict[str, TemplateProject]]):
    """Runs project pipeline creation/management.

    Args:
      proxy: the proxy for the Flywheel instance
      project_list: the list of project input
      admin_users: the list of admin users
      template_map: map from datatype name to template projects
    """

    for project_doc in project_list:
        project = Project.create(project_doc)
        project_mapper = ProjectMappingAdaptor(project=project,
                                               flywheel_proxy=proxy,
                                               admin_users=admin_users,
                                               template_map=template_map)
        project_mapper.create_project_pipelines()
