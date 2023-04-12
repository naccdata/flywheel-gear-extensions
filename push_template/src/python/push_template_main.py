"""Function to push template projects to pipeline projects in the center groups
of the the Flywheel instance."""
import logging
from typing import Dict

from centers.center_group import CenterGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from projects.template_project import TemplateProject

log = logging.getLogger(__name__)


def run(*, proxy: FlywheelProxy, center_tag_pattern: str,
        template_map: Dict[str, Dict[str, TemplateProject]]) -> None:
    """Runs template copying process.

    Args:
      proxy: the proxy for the Flywheel instance
      center_tag_pattern: regex pattern to match center tags
      template_map: map from datatype name to template projects
    """
    group_list = proxy.find_groups_by_tag(center_tag_pattern)
    if not group_list:
        log.warning('no centers found matching tag pattern %s',
                    center_tag_pattern)
        return

    for group in group_list:
        center = CenterGroup(group=group, proxy=proxy)
        center.apply_template_map(template_map)
