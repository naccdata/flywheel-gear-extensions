"""Defines REDCap Project Creation."""

import logging
from typing import Dict, List, Optional, Tuple

from centers.center_group import (CenterGroup, REDCapFormProject,
                                  REDCapProjectInput, StudyREDCapMetadata)
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import (REDCapConnection, REDCapConnectionError,
                                      REDCapSuperUserConnection)

log = logging.getLogger(__name__)


def save_project_api_token(parameter_store: ParameterStore, base_path: str,
                           token: str, url: str) -> Optional[int]:
    """Retrieve the newly created REDCap PID using the project api token. Save
    the project api token for the new project in AWS parameter store.

    Args:
        parameter_store: AWS parameter store connection
        base_path: AWS parameter store path prefix
        token: REDCap API token for the project
        url: REDCap API url

    Returns:
        Optional[int]: New REDCap project PID if successful
    """

    try:
        redcap_con = REDCapConnection(token=token, url=url)
    except REDCapConnectionError as error:
        log.error(error)
        return None

    try:
        parameter_store.set_redcap_project_prameters(base_path=base_path,
                                                     pid=redcap_con.pid,
                                                     url=url,
                                                     token=token)
    except ParameterError as error:
        log.error(error)
        return None

    return redcap_con.pid


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

    redcap_metadata = []
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
                    if module.label in xml_templates:
                        project_xml = xml_templates[module.label]
                    else:
                        log.error('Cannot find xml template for %s/%s/%s',
                                  center, project_lbl, module.label)
                        errors = True
                        continue

                redcap_prj_title = f'{group_adaptor.label} {module.title}'
                try:
                    api_key = redcap_super_con.create_project(
                        title=redcap_prj_title, project_xml=project_xml)
                except REDCapConnectionError as error:
                    log.error(error)
                    errors = True
                    continue

                redcap_pid = save_project_api_token(parameter_store, base_path,
                                                    api_key,
                                                    redcap_super_con.url)
                if redcap_pid:
                    module_obj = REDCapFormProject(redcap_pid=redcap_pid,
                                                   label=module.label,
                                                   report_id=None)
                    project_object.projects.append(module_obj)
                else:
                    errors = True
                    continue

            # Update REDCap project metadata in Flywheel
            if len(project_object.projects) > 0:
                center_group = CenterGroup.create_from_group_adaptor(
                    adaptor=group_adaptor)
                center_group.add_redcap_project(project_object)
                redcap_metadata.append(project_object)

    return errors, redcap_metadata
