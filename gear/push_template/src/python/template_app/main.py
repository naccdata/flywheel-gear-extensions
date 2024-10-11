"""Function to push template projects to pipeline projects in the center groups
of the the Flywheel instance."""
import logging

from centers.nacc_group import NACCGroup
from projects.template_project import TemplateProject

log = logging.getLogger(__name__)


def run(*, admin_group: NACCGroup, new_only: bool,
        template: TemplateProject) -> None:
    """Applies the template to all matching projects in centers managed by the
    admin group.

    Args:
      proxy: the proxy for the Flywheel instance
      center_tag_pattern: regex pattern to match center tags
      template_map: map from datatype name to template projects
    """
    center_list = admin_group.get_centers()
    if not center_list:
        log.warning('no groups found for centers')
        return

    for center in center_list:
        if new_only and 'new-center' not in center.get_tags():
            continue

        center.apply_template(template)
        # TODO: remove 'new-center' tag
