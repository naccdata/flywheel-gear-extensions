"""Entry script for REDCap to Flywheel Transfer."""

import logging
import sys
from typing import Any, Dict, Optional, Tuple

from centers.center_group import (
    CenterError,
    CenterGroup,
    FormIngestProjectMetadata,
    REDCapFormProjectMetadata,
)
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import GroupAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import REDCapReportConnection

from redcap_fw_transfer_app.main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def get_destination_group_and_project(dest_container: Any) -> Tuple[str, str]:
    """Find the flywheel group id and project id for the destination project.

    Args:
        dest_container: Flywheel container in which the gear is triggered

    Returns:
        Tuple[str, str]: group id, project id

    Raises:
        GearExecutionError if any error occurred while retrieving parent info
    """

    if not dest_container:
        raise GearExecutionError('Gear destination not set')

    if dest_container.container_type == 'project':
        project_id = dest_container.id
        group_id = dest_container.group
    elif dest_container.container_type in ('session', 'acquisition'):
        project_id = dest_container.parents.project
        group_id = dest_container.parents.group
    else:
        raise GearExecutionError(
            f'Invalid gear destination type {dest_container.container_type}')

    return group_id, project_id


def get_redcap_projects_metadata(
        *, fw_proxy: FlywheelProxy, group_adaptor: GroupAdaptor,
        project_label: str) -> Dict[str, REDCapFormProjectMetadata]:
    """Retrieve the info on source REDCap projects to transfer the data from.
    REDCap->FW mapping info is included in each center's metadata project.

    Args:
        fw_proxy: Flywheel proxy
        group_adaptor: Flywhee adaptor for the center group
        project_label: Flywheel ingest project label to upload data

    Returns:
        Dict[str, REDCapFormProject]: REDCap project info by module

    Raises:
        GearExecutionError if any error occurred while parsing metadata
    """

    redcap_projects = {}

    try:
        center_group = CenterGroup.create_from_group_adaptor(
            adaptor=group_adaptor)
        center_metadata = center_group.get_project_info()
    except CenterError as error:
        raise GearExecutionError(
            f'Error in retrieving center metadata: {error}') from error

    matches = 0
    for study, study_metadata in center_metadata.studies.items():
        # there should be only one study with matching project label
        # iterate until a match found
        project_metadata = study_metadata.get_ingest(project_label)
        if (not project_metadata
                or not isinstance(project_metadata, FormIngestProjectMetadata)
                or not project_metadata.redcap_projects):
            continue

        matches += 1
        log.info(
            'REDCap projects metadata found for center: %s, '
            'study: %s, project: %s', group_adaptor.id, study, project_label)
        redcap_projects = project_metadata.redcap_projects

    if matches > 1:
        raise GearExecutionError(
            'More than one match found for project '
            f'{project_label} in center {group_adaptor.id} metadata')

    return redcap_projects


class REDCapFlywheelTransferVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the redcap_fw_transfer app."""

    def __init__(self, client: ClientWrapper, parameter_store: ParameterStore,
                 param_path: str):
        """
        Args:
            client: Flywheel SDK client wrapper
            parameter_store: AWS parameter store connection
            param_path: AWS parameter path for REDCap credentials
        """
        super().__init__(client=client)
        self.__param_store = parameter_store
        self.__param_path = param_path

    @classmethod
    def create(
        cls, context: GearToolkitContext,
        parameter_store: Optional[ParameterStore]
    ) -> 'REDCapFlywheelTransferVisitor':
        """Creates a redcap_fw_transfer execution visitor.

        Args:
          context: the gear context
          parameter_store: AWS parameter store connection

        Raises:
          GearExecutionError if any error occurred while parsing gear configs
        """
        assert parameter_store, "Parameter store expected"

        try:
            param_path: str = get_config(gear_context=context,
                                         key='parameter_path')
        except ConfigParseError as error:
            raise GearExecutionError(
                f'Incomplete configuration: {error.message}') from error

        client_wrapper = GearBotClient.create(context=context,
                                              parameter_store=parameter_store)

        return REDCapFlywheelTransferVisitor(client=client_wrapper,
                                             parameter_store=parameter_store,
                                             param_path=param_path)

    # pylint: disable=(too-many-locals)
    def run(self, context: GearToolkitContext):
        """Runs the redcap_fw_transfer app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if error occurrs while transferring data
        """

        assert context, 'Gear context required'

        try:
            dest_container = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error

        group_id, project_id = get_destination_group_and_project(
            dest_container)
        group = self.proxy.find_group(group_id)
        if not group:
            raise GearExecutionError(f'Cannot find Flywheel group {group_id}')
        project = self.proxy.get_project_by_id(project_id)
        if not project:
            raise GearExecutionError(
                f'Cannot find Flywheel project {project_id}')

        redcap_projects = get_redcap_projects_metadata(
            group_adaptor=group, project_label=project.label)

        if not redcap_projects:
            raise GearExecutionError(
                'REDCap project information not found for '
                f'{group_id}/{project.label}')

        failed_count = 0
        for module, redcap_project in redcap_projects.items():
            if (not redcap_project.label or not redcap_project.redcap_pid
                    or not redcap_project.report_id):
                log.error(
                    'Incomplete REDCap project info in %s/metadata '
                    'for module %s', group_id, module)
                failed_count += 1
                continue

            try:
                redcap_params = self.__param_store.get_redcap_project_parameters(
                    base_path=self.__param_path,
                    pid=redcap_project.redcap_pid,
                    report_id=redcap_project.report_id)
                redcap_report_con = REDCapReportConnection.create_from(
                    redcap_params)
            except ParameterError as error:
                log.error(
                    'Error in retrieving REDCap report credentials '
                    'for project %s module %s: %s', redcap_project.redcap_pid,
                    redcap_project.label, error)
                failed_count += 1
                continue

            try:
                run(gear_context=context,
                    redcap_con=redcap_report_con,
                    redcap_pid=str(redcap_project.redcap_pid),
                    module=redcap_project.label,
                    fw_group=group_id,
                    fw_project=project)
            except GearExecutionError as error:
                log.error(
                    'Error in ingesting module %s from REDCap project %s: %s',
                    redcap_project.label, redcap_project.redcap_pid, error)
                failed_count += 1
                continue

        if failed_count > 0:
            raise GearExecutionError(
                f'Failed to ingest data for {failed_count} module(s)')


def main():
    """Main method for REDCap to Flywheel Transfer."""

    GearEngine.create_with_parameter_store().run(
        gear_type=REDCapFlywheelTransferVisitor)


if __name__ == "__main__":
    main()
