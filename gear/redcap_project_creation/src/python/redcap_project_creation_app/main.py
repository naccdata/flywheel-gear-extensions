"""Defines REDCap Project Creation."""

import logging
from typing import Dict, List, Optional, Tuple

from centers.center_group import (
    CenterError,
    CenterGroup,
    REDCapFormProjectMetadata,
    REDCapProjectInput,
    StudyREDCapMetadata,
)
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import (
    REDCapConnection,
    REDCapConnectionError,
    REDCapSuperUserConnection,
)
from redcap.redcap_project import REDCapProject

log = logging.getLogger(__name__)


def setup_new_project_elements(parameter_store: ParameterStore, base_path: str,
                               token: str, url: str) -> Optional[int]:
    """Set up elements required to access the new REDCap project.

        - Retrieve the newly created REDCap PID using the project api token.
        - Save the project api token for the new project in AWS parameter store.
        - Add nacc gearbot user to the project

    Args:
        parameter_store: AWS parameter store connection
        base_path: AWS parameter store path prefix
        token: REDCap API token for the project
        url: REDCap API url

    Returns:
        Optional[int]: New REDCap project PID if successful
    """

    try:
        redcap_prj = REDCapProject.create(
            REDCapConnection(token=token, url=url))
        redcap_prj.add_gearbot_user_to_project()
    except REDCapConnectionError as error:
        log.error(error)
        return None

    try:
        parameter_store.set_redcap_project_parameters(base_path=base_path,
                                                      pid=redcap_prj.pid,
                                                      url=url,
                                                      token=token)
    except ParameterError as error:
        log.error(error)
        return None

    return redcap_prj.pid


# pylint: disable=(too-many-locals)
def run(
    *, proxy: FlywheelProxy, parameter_store: ParameterStore, base_path: str,
    redcap_super_con: REDCapSuperUserConnection,
    study_info: StudyREDCapMetadata, use_template: bool,
    xml_templates: Optional[Dict[str, str]]
) -> Tuple[bool, List[REDCapProjectInput]]:
    """Create REDCap projects using super API token, store project API token in
    AWS parameter store, update REDCap project info in Flywheel metadata.

    Args:
        proxy: Flywheel proxy
        parameter_store: AWS parameter store connection
        base_path: AWS parameter store path prefix
        redcap_super_con: REDCap super user API connection
        study_info: Info on which REDCap projects to be created
        use_template: Whether to use XML template for project creation
        xml_templates[Optional]: REDCap XML templates by module

    Returns:
        bool: True if there are no errors, else False
        Optional[str]: YAML text of REDCap project metadata
    """

    redcap_metadata: List[REDCapProjectInput] = []
    errors = False

    for center in study_info.centers:
        group_adaptor = proxy.find_group(center)
        if not group_adaptor:
            log.error('Cannot find Flywheel group for center id %s', center)
            errors = True
            continue

        for project in study_info.projects:
            project_lbl = project.project_label
            if not group_adaptor.find_project(label=project_lbl):
                log.error('Cannot find project %s in center %s', project_lbl,
                          center)
                errors = True
                continue

            project_object = REDCapProjectInput(center_id=center,
                                                study_id=study_info.study_id,
                                                project_label=project_lbl,
                                                projects=[])

            for module in project.modules:
                project_xml = None
                if use_template and xml_templates:
                    if module.label not in xml_templates:
                        log.error('Cannot find xml template for %s/%s/%s',
                                  center, project_lbl, module.label)
                        errors = True
                        continue

                    project_xml = xml_templates[module.label]

                redcap_prj_title = f'{group_adaptor.label} {module.title}'
                try:
                    api_key = redcap_super_con.create_project(
                        title=redcap_prj_title, project_xml=project_xml)
                except REDCapConnectionError as error:
                    log.error(error)
                    errors = True
                    continue

                redcap_pid = setup_new_project_elements(
                    parameter_store, base_path, api_key, redcap_super_con.url)
                if not redcap_pid:
                    errors = True
                    continue

                module_obj = REDCapFormProjectMetadata(redcap_pid=redcap_pid,
                                                       label=module.label,
                                                       report_id=None)
                project_object.projects.append(module_obj)

            update_redcap_metadata(redcap_metadata=redcap_metadata,
                                   group_adaptor=group_adaptor,
                                   project_object=project_object)

    return errors, redcap_metadata


def update_redcap_metadata(*, redcap_metadata: List[REDCapProjectInput],
                           group_adaptor: GroupAdaptor,
                           project_object: REDCapProjectInput):
    """Updates the REDCap project metadata in Flywheel.

    Args:
      redcap_metadata: the project metadata
      group_adapter: the group for the center
      project_lbl: the project label
      project_object: the project
    """
    if len(project_object.projects) > 0:
        try:
            center_group = CenterGroup.get_center_group(adaptor=group_adaptor)
            center_group.add_redcap_project(project_object)
        except CenterError:
            log.error('Failed to update REDCap project metadata for %s/%s',
                      group_adaptor.label, project_object.project_label)

        redcap_metadata.append(project_object)
