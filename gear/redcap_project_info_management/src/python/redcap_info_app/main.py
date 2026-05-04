"""Defines REDCap Project Info Management."""

import logging

from centers.center_group import REDCapProjectInput
from centers.nacc_group import NACCGroup

log = logging.getLogger(__name__)


def run(*, project_list: list[REDCapProjectInput], admin_group: NACCGroup):
    """Adds REDCap project information from the list to the center info object.

    Args:
      project_list: the list of REDCap project information
      admin_group: the NACC group object
    """

    center_map = admin_group.get_center_map()
    id_map = {info.group: info for info in center_map.centers.values()}

    for project_input in project_list:
        log.info("Adding info to center %s", project_input.center_id)
        center_info = id_map.get(project_input.center_id)
        if not center_info:
            log.error("Center %s not found", project_input.center_id)
            continue

        center_group = admin_group.get_center(center_info.adcid)
        if not center_group:
            log.error("Center with ADCID %s not found", center_info.adcid)
            continue

        center_group.add_redcap_project(project_input)
