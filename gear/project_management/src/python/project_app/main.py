"""Defines project management computation."""

import logging
from typing import List

from centers.nacc_group import NACCGroup
from flywheel.models.group_role import GroupRole
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from projects.study import Study
from projects.study_mapping import (
    AggregationStudyMapping,
    DistributionStudyMapping,
    StudyMappingAdaptor,
)

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


def run(*, proxy: FlywheelProxy, admin_group: NACCGroup,
        study_list: List[Study]):
    """Runs project pipeline creation/management.

    Args:
      proxy: the proxy for the Flywheel instance
      admin_group: the administrative group
      study_list: the list of input study objects
    """
    for study in study_list:
        mapper: StudyMappingAdaptor
        if study.mode == 'aggregation':
            mapper = AggregationStudyMapping(study=study,
                                             flywheel_proxy=proxy,
                                             admin_group=admin_group)

        if study.mode == 'distribution':
            mapper = DistributionStudyMapping(study=study,
                                              flywheel_proxy=proxy)

        mapper.create_study_pipelines()
