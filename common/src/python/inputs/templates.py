"""Functions to pull information from template projects."""
import logging
import re
from collections import defaultdict
from typing import Dict

import flywheel
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from projects.template_project import TemplateProject

log = logging.getLogger(__name__)


def get_template_projects(
        *, group: flywheel.Group,
        proxy: FlywheelProxy) -> Dict[str, Dict[str, TemplateProject]]:
    """Returns template projects from the group on the indicated FW instance.

    Expects template project names to match `<datatype>-<stage>-template`.

    Organizes projects by stage name, and then by datatype name.

    Args:
      group: the flywheel group containing the template projects
      proxy: the proxy for the flywheel instance
    Returns:
      dictionary of template projects indexed by stage and datatype
    """
    template_map: Dict[str, Dict[str, TemplateProject]] = defaultdict(dict)
    if group:
        template_matcher = re.compile(r"^((\w+)-)?(\w+)-template$")
        # group 2 datatype
        # group 3 stage
        for project in group.projects():
            match = template_matcher.match(project.label)
            if match:
                datatype = match.group(2)
                if not datatype:
                    # accepted stage has no datatype, set to 'all'
                    datatype = 'all'
                stage = match.group(3)

                # TODO: stage list needs to come from elsewhere
                if stage not in ['accepted', 'ingest', 'retrospective']:
                    log.error(
                        'unrecognized pipeline stage %s'
                        ' in template project %s', stage, project.label)
                    continue

                stage_map = template_map[datatype]
                stage_map[stage] = TemplateProject(project=project,
                                                   proxy=proxy)
                template_map[datatype] = stage_map

    return template_map
