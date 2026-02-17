"""Reads a YAML file with project info.

project - name of project
centers - array of centers
    center-id - the group ID of center
    adcid - the ADC ID used to code data
    name - name of center
    is-active - whether center is active, has users if True
datatypes - array of datatype names (form, dicom)
mode - string indicating 'aggregation' or 'distribution'
published - boolean indicating whether data is to be published
"""

import logging
from pathlib import Path
from typing import List, Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore
from inputs.yaml import YAMLReadError, load_all_from_stream
from projects.study import StudyModel

from project_app.main import run

log = logging.getLogger(__name__)


class ProjectCreationVisitor(GearExecutionEnvironment):
    """Defines the project management gear."""

    def __init__(self, admin_id: str, client: ClientWrapper, project_filepath: Path):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__project_filepath = project_filepath

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "ProjectCreationVisitor":
        """Creates a projection creation execution visitor.

        Args:
          context: the gear context
        Returns:
          the project creation visitor
        Raises:
          GearExecutionError if the project file cannot be loaded
        """
        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        project_filepath = context.config.get_input_path("project_file")
        if not project_filepath:
            raise GearExecutionError("No project file provided")

        admin_id = context.config.opts.get("admin_group", "nacc")

        return ProjectCreationVisitor(
            admin_id=admin_id, client=client, project_filepath=project_filepath
        )

    def __get_study_list(self, project_filepath: Path) -> List[StudyModel]:
        try:
            with project_filepath.open("r", encoding="utf-8-sig") as stream:
                project_list = load_all_from_stream(stream)
        except YAMLReadError as error:
            raise GearExecutionError(
                f"Unable to read YAML file {project_filepath}: {error}"
            ) from error
        if not project_list:
            raise GearExecutionError("Failed to read project file")

        return [StudyModel.create(study_doc) for study_doc in project_list]

    def run(self, context: GearContext) -> None:
        """Executes the gear.

        Args:
            context: the gear execution context

        Raises:
            AssertionError: If admin group ID or project list is not provided.
        """
        run(
            proxy=self.proxy,
            admin_group=self.admin_group(admin_id=self.__admin_id),
            study_list=self.__get_study_list(self.__project_filepath),
        )


def main():
    """Main method to run the project creation gear."""

    GearEngine.create_with_parameter_store().run(gear_type=ProjectCreationVisitor)


if __name__ == "__main__":
    main()
