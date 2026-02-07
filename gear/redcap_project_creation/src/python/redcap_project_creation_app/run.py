"""Entry script for REDCap Project Creation."""

import logging
from pathlib import Path
from typing import Dict, Optional

import yaml
from centers.center_group import (
    CenterMetadata,
    FormIngestProjectMetadata,
    REDCapProjectInput,
    StudyREDCapMetadata,
    StudyREDCapProjectsList,
)
from flywheel import Project
from flywheel.rest import ApiException
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream
from keys.keys import DefaultValues
from pydantic import ValidationError
from redcap_api.redcap_connection import REDCapSuperUserConnection
from redcap_api.redcap_parameter_store import REDCapParameters

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
                xml_file = prefix.lower() + "-redcap-template.xml"
                try:
                    xml = admin_project.read_file(xml_file)
                except ApiException as error:
                    log.error("Failed to read template file %s - %s", xml_file, error)
                    return None
                xml_templates[module.label] = str(xml, "utf-8")

    return xml_templates


def validate_input_data(input_file_path: Path) -> Optional[StudyREDCapMetadata]:
    """Validates the input file.

    Args:
        input_file_path: Gear input file path

    Returns:
        Optional[StudyREDCapMetadata]: Info on REDCap projects to be created
    """

    try:
        with input_file_path.open("r", encoding="utf-8 ") as input_file:
            input_data = load_from_stream(input_file)
    except YAMLReadError as error:
        log.error("Failed to read the input file - %s", error)
        return None

    try:
        study_info = StudyREDCapMetadata.model_validate(input_data)
    except ValidationError as error:
        log.error("Input data not in expected format - %s", error)
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
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "REDCapProjectCreation":
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

        client_wrapper = GearBotClient.create(
            context=context, parameter_store=parameter_store
        )

        return REDCapProjectCreation(
            client=client_wrapper, parameter_store=parameter_store
        )

    def __write_out_file(  # noqa: C901
        self,
        context: GearContext,
        admin_group_id: str,
        study_id: str,
        filename: str,
    ):
        """Write REDCap project metadata to output yaml file.

        Args:
            context: gear context
            admin_group_id: Flywheel admin group ID
            study_id: Study id
            filename: output file name
        """

        nacc_group = self.admin_group(admin_id=admin_group_id)
        centers = nacc_group.get_center_map().centers
        if not centers:
            log.error("Center information not found in %s/metadata", admin_group_id)
            return

        study_redcap_metadata = StudyREDCapProjectsList([])
        # collect updated REDCap project mapping metadata for the study
        for center in centers.values():
            if not center.active:
                continue

            assert center.group is not None
            group_adaptor = self.proxy.find_group(center.group)
            if not group_adaptor:
                log.warning("Cannot find Flywheel group for Center ID %s", center.group)
                continue

            center_metadata_prj = group_adaptor.find_project(
                DefaultValues.METADATA_PRJ_LBL
            )
            if not center_metadata_prj:
                log.warning("Cannot find metadata project in group %s", center.group)
                continue

            info = center_metadata_prj.get_info()
            if not info or "studies" not in info:
                log.warning("Studies metadata not found in %s/metadata", center.group)
                continue

            try:
                center_metadata = CenterMetadata.model_validate(info)
            except ValidationError as error:
                log.error(
                    "Studies info in %s/metadata does not match expected format: %s",
                    center.group,
                    error,
                )
                continue

            study_metadata = center_metadata.studies.get(study_id)
            if not study_metadata:
                log.info("Study %s not found in %s/metadata", study_id, center.group)
                continue

            for ingest_project in study_metadata.ingest_projects.values():
                if (
                    not isinstance(ingest_project, FormIngestProjectMetadata)
                    or not ingest_project.redcap_projects
                ):
                    continue

                redcap_projects = []
                for redcap_project in ingest_project.redcap_projects.values():
                    redcap_projects.append(redcap_project)

                study_redcap_metadata.append(
                    REDCapProjectInput(
                        center_id=center.group,
                        study_id=study_id,
                        project_label=ingest_project.project_label,
                        projects=redcap_projects,
                    )
                )

        # write updated metadata to output file
        if len(study_redcap_metadata.root) > 0:
            yaml_text = yaml.safe_dump(
                data=study_redcap_metadata.model_dump(serialize_as_any=True),
                allow_unicode=True,
                default_flow_style=False,
            )

            out_filename = f"{study_id}-{filename}"
            with context.open_output(
                out_filename, mode="w", encoding="utf-8"
            ) as out_file:
                out_file.write(yaml_text)

    # pylint: disable = (too-many-locals)
    def run(self, context: GearContext) -> None:  # noqa: C901
        """Invoke the redcap project creation app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if errors occur while creating the projects
        """
        input_file_path = context.config.get_input_path("input_file")
        if not input_file_path:
            raise GearExecutionError("No input file provided")

        study_info = validate_input_data(input_file_path)
        if not study_info:
            raise GearExecutionError(
                f"Error(s) in reading input file - {input_file_path}"
            )

        try:
            super_token_path: str = get_config(
                gear_context=context,
                key="super_token_path",
                default="/redcap/aws/super",
            )
            token_path_prefix: str = get_config(
                gear_context=context, key="project_token_path", default="/redcap/aws"
            )
            admin_lookup: str = get_config(
                gear_context=context, key="admin_project", default="nacc/project-admin"
            )
            use_xml_template: bool = get_config(
                gear_context=context, key="use_xml_template", default=True
            )
            output_filename: str = get_config(
                gear_context=context,
                key="output_file_name",
                default="ingest-projects-redcap-metadata.yaml",
            )

            dry_run: bool = get_config(
                gear_context=context, key="dry_run", default=False
            )
        except ConfigParseError as error:
            raise GearExecutionError(f"Incomplete configuration - {error}") from error

        try:
            admin_project: Project = self.proxy.lookup(admin_lookup)
        except ApiException as error:
            raise GearExecutionError(f"Cannot find admin project - {error}") from error

        # Just update the REDCap metadata file and exit
        if dry_run:
            log.info(
                "Dry run - updating the metadata file %s-%s",
                study_info.study_id,
                output_filename,
            )
            self.__write_out_file(
                context=context,
                admin_group_id=admin_project.group,
                study_id=study_info.study_id,
                filename=output_filename,
            )
            exit(0)

        if use_xml_template:
            xml_templates = get_xml_templates(admin_project, study_info)
            if not xml_templates:
                raise GearExecutionError("Failed to load required XML template files")

        try:
            super_credentials = self.__param_store.get_parameters(
                param_type=REDCapParameters, parameter_path=super_token_path
            )
        except ParameterError as error:
            raise GearExecutionError(error) from error

        redcap_super_con = REDCapSuperUserConnection.create_from(super_credentials)

        errors, updated = run(
            proxy=self.proxy,
            parameter_store=self.__param_store,
            base_path=token_path_prefix,
            redcap_super_con=redcap_super_con,
            study_info=study_info,
            use_template=use_xml_template,
            xml_templates=xml_templates,
        )

        if updated > 0:
            self.__write_out_file(
                context=context,
                admin_group_id=admin_project.group,
                study_id=study_info.study_id,
                filename=output_filename,
            )

        if errors:
            raise GearExecutionError("Errors occurred while creating REDCap projects")


def main():
    """Main method for REDCap Project Creation."""

    GearEngine().create_with_parameter_store().run(gear_type=REDCapProjectCreation)


if __name__ == "__main__":
    main()
