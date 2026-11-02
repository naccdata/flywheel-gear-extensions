"""Function to push template projects to pipeline projects in the center groups
of the the Flywheel instance."""

import logging
from typing import List

from centers.center_group import TemplateApplicationFailure
from centers.nacc_group import NACCGroup
from projects.template_project import TemplateError, TemplateProject

log = logging.getLogger(__name__)


def run(*, admin_group: NACCGroup, new_only: bool, template: TemplateProject) -> None:
    """Applies the template to all matching projects in centers managed by the
    admin group.

    Attempts every matching project in every center. Transport/timeout failures
    for individual projects are accumulated rather than aborting the run, so a
    single slow project does not discard work already applied to other projects.
    After attempting all projects, raises a TemplateError listing the failed
    projects if any failed, so the gear exits with a non-zero status (the run is
    not reported as successful unless every project succeeded).

    Args:
      admin_group: the admin group managing the centers
      new_only: whether to apply only to centers tagged 'new-center'
      template: the template project to apply
    Raises:
      TemplateError: if the template could not be applied to one or more
        projects
    """
    center_list = admin_group.get_centers()
    if not center_list:
        log.warning("no groups found for centers")
        return

    failures: List[TemplateApplicationFailure] = []
    for center in center_list:
        if new_only and "new-center" not in center.get_tags():
            continue

        failures.extend(center.apply_template(template))
        # TODO: remove 'new-center' tag

    if failures:
        failure_list = "\n".join(f"  {failure}" for failure in failures)
        raise TemplateError(
            f"Failed to apply template to {len(failures)} project(s):\n{failure_list}"
        )
