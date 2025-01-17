"""Entry script for REDCap Project Creation."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

# import yaml
from centers.center_group import REDCapProjectInput, StudyREDCapMetadata
from flywheel import Project
from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore, REDCapParameters
from inputs.yaml import YAMLReadError, load_from_stream
from pydantic import ValidationError
from redcap.redcap_connection import REDCapSuperUserConnection

from redcap_project_creation_app.main import run

log = logging.getLogger(__name__)


def get_xml_templates(
    admin_project: Project,
    study_info: StudyREDCapMetadata,
) -> Optional[Dict[str, str]]:
    """Load the REDCap XML templates for the modules from the admin project.

    Args:
        admin_project: Flywheel admin project
        study_info: REDCap metadata for the study

    Returns:
        Optional[Dict[str, str]]: XML templates by module
    """
    xml_templates = {}
    for project in study_info.projects:
        for module in project.modules:
            if module.label not in xml_templates:
                prefix = module.template if module.template else module.label
                xml_file = prefix.lower() + '-redcap-template.xml'
                try:
                    xml = admin_project.read_file(xml_file)
                except ApiException as error:
                    log.error('Failed to read template file %s - %s', xml_file,
                              error)
                    return None
                xml_templates[module.label] = str(xml, 'utf-8')

    return xml_templates


def validate_input_data(input_file_path: str) -> Optional[StudyREDCapMetadata]:
    """Validates the input file.

    Args:
        input_file_path: Gear input file path

    Returns:
        Optional[StudyREDCapMetadata]: Info on REDCap projects to be created
    """

    try:
        with open(input_file_path, 'r', encoding='utf-8 ') as input_file:
            input_data = load_from_stream(input_file)
    except YAMLReadError as error:
        log.error('Failed to read the input file - %s', error)
        return None

    try:
        study_info = StudyREDCapMetadata.model_validate(input_data)
    except ValidationError as error:
        log.error('Input data not in expected format - %s', error)
        return None

    return study_info


class REDCapProjectCreation(GearExecutionEnvironment):
    """Visitor for the redcap project creation gear."""

    def __init__(self, client: ClientWrapper, parameter_store: ParameterStore):
        super().__init__(client=client)
        self.__param_store = parameter_store

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'REDCapProjectCreation':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store

        Returns:
          the execution environment

        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        client_wrapper = GearBotClient.create(context=context,
                                              parameter_store=parameter_store)

        return REDCapProjectCreation(client=client_wrapper,
                                     parameter_store=parameter_store)

    def __write_out_file(self, context: GearToolkitContext,
                         fw_metadata: List[REDCapProjectInput], filename: str):
        """Write generated REDCap project metadata to output yaml file.

        Args:
            context: gear context
            fw_metadata: REDCap project metadata
            filename: output file name
        """
        # TODO - fix writing generated metadata to yaml file
        # yaml_text = yaml.safe_dump(data=fw_metadata,
        #                            allow_unicode=True,
        #                            default_flow_style=False)

        # with context.open_output(fname, mode='w',
        #                          encoding='utf-8') as out_file:
        #     out_file.write(yaml_text)

    # pylint: disable = (too-many-locals)
    def run(self, context: GearToolkitContext) -> None:
        """Invoke the redcap project creation app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if errors occur while creating the projects
        """
        input_file_path = context.get_input_path('input_file')
        if not input_file_path:
            raise GearExecutionError('No input file provided')

        study_info = validate_input_data(input_file_path)
        if not study_info:
            raise GearExecutionError(
                f'Error(s) in reading input file - {input_file_path}')

        try:
            super_token_path: str = get_config(gear_context=context,
                                               key='super_token_path',
                                               default='/redcap/aws/super')
            token_path_prefix: str = get_config(gear_context=context,
                                                key='project_token_path',
                                                default='/redcap/aws')
            admin_id: str = get_config(gear_context=context,
                                       key='admin_project',
                                       default='nacc/project-admin')
            use_xml_template: bool = get_config(gear_context=context,
                                                key='use_xml_template',
                                                default=True)
            output_prefix: str = get_config(gear_context=context,
                                            key='output_file_prefix',
                                            default='redcap-projects')
        except ConfigParseError as error:
            raise GearExecutionError(
                f'Incomplete configuration - {error}') from error

        try:
            admin_project = self.client.client.lookup(admin_id)
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find admin project - {error}') from error

        if use_xml_template:
            xml_templates = get_xml_templates(admin_project, study_info)
            if not xml_templates:
                raise GearExecutionError(
                    'Failed to load required XML template files')

        try:
            super_credentials = self.__param_store.get_parameters(
                param_type=REDCapParameters, parameter_path=super_token_path)
        except ParameterError as error:
            raise GearExecutionError(error) from error

        redcap_super_con = REDCapSuperUserConnection.create_from(
            super_credentials)

        errors, fw_metadata = run(proxy=self.proxy,
                                  parameter_store=self.__param_store,
                                  base_path=token_path_prefix,
                                  redcap_super_con=redcap_super_con,
                                  study_info=study_info,
                                  use_template=use_xml_template,
                                  xml_templates=xml_templates)

        if len(fw_metadata) > 0:
            tstmp = datetime.now().strftime("%Y%m%d-%H%M%S")
            fname = f'{output_prefix} - {study_info.study_id} - {tstmp}.yaml'
            self.__write_out_file(context=context,
                                  fw_metadata=fw_metadata,
                                  filename=fname)

        if errors:
            raise GearExecutionError(
                'Errors occurred while creating REDCap projects')


def main():
    """Main method for REDCap Project Creation."""

    GearEngine().create_with_parameter_store().run(
        gear_type=REDCapProjectCreation)


if __name__ == "__main__":
    main()
