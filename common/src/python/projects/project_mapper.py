"""Maps ADCID to projects."""
import logging
from typing import Dict, List, Optional

from centers.center_group import CenterError, CenterGroup
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor

log = logging.getLogger(__name__)


def build_project_map(
        *,
        proxy: FlywheelProxy,
        destination_label: str,
        center_filter: Optional[List[str]] = None) -> Dict[str, ProjectAdaptor]:
    """Builds a map from adcid to the project of center group with the given
    label.

    Args:
      proxy: the flywheel instance proxy
      destination_label: the project of center to map to
      center_tag_pattern: the regex for adcid-tags
      center_filter: Optional list of ADCIDs to filter on for a mapping subset
    Returns:
      dictionary mapping from adcid to group
    """
    center_map = NACCGroup.create(proxy=proxy).\
        get_center_map(center_filter=center_filter)

    if not center_map:
        log.warning('No centers found to build project map')
        return {}

    project_map = {}
    try:
        for adcid, center_info in center_map.centers.items():
            group = CenterGroup.create_from_center(center=center_info,
                                                   proxy=proxy)
            project = group.find_project(destination_label)
            if not project:
                continue
            project_map[f'adcid-{adcid}'] = project

    except CenterError as error:
        log.error('failed to create center from group: %s', error.message)
        return {}

    if not project_map:
        log.warning('No projects found while building project map')

    return project_map
