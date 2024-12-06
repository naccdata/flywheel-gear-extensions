"""Maps ADCID to projects."""
import logging
import re
from typing import Dict, List, Optional

from centers.center_group import CenterError, CenterGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor

log = logging.getLogger(__name__)


def build_project_map(
        *,
        proxy: FlywheelProxy,
        destination_label: str,
        center_tag_pattern=r'adcid-\d+',
        centers: Optional[List[int]] = None) -> Dict[str, ProjectAdaptor]:
    """Builds a map from adcid to the project of center group with the given
    label.

    Args:
      proxy: the flywheel instance proxy
      destination_label: the project of center to map to
      center_tag_pattern: the regex for adcid-tags
      centers: the subset of centers to return; if not specified, returns all
    Returns:
      dictionary mapping from adcid to group
    """
    try:
        group_list = [
            CenterGroup.create_from_group(group=group, proxy=proxy)
            for group in proxy.find_groups_by_tag(center_tag_pattern)
        ]
    except CenterError as error:
        log.error('failed to create center from group: %s', error.message)
        return {}

    if not group_list:
        log.warning('no centers found matching tag pattern %s',
                    center_tag_pattern)
        return {}

    # TODO: would be nice to filter before/during the above but doesn't
    # seem straightforward due to the use of finding groups by tag
    if centers:
        group_list = [x for x in group_list if x.adcid in centers]

    project_map = {}
    for group in group_list:
        project = group.find_project(destination_label)
        if not project:
            continue

        pattern = re.compile(center_tag_pattern)
        tags = list(filter(pattern.match, group.get_tags()))
        for tag in tags:
            project_map[tag] = project

    return project_map
