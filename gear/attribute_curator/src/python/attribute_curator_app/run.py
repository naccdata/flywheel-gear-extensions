"""Entry script for UDS Curator."""

import logging
from pathlib import Path
from typing import Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from nacc_attribute_deriver.attribute_deriver import AttributeDeriver

from attribute_curator_app.main import run

log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(self, client: ClientWrapper, project: ProjectAdaptor,
                 derive_rules: InputFileWrapper,
                 filename_pattern: str):
        super().__init__(client=client)
        self.__project = project
        self.__derive_rules = derive_rules
        self.__filename_pattern = filename_pattern

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'AttributeCuratorVisitor':
        """Creates a UDS Curator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)
        proxy = client.get_proxy()

        filename_pattern = context.config.get('filename_pattern', "*.json")

        derive_rules = InputFileWrapper.create(input_name='derive_rules',
                                               context=context)
        if not derive_rules:
            raise GearExecutionError("Derive rules CSV required")

        fw_project = derive_rules.get_parent_project(proxy=proxy)

        try:
            destination = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error
        if destination.container_type != 'analysis':  # type: ignore
            raise GearExecutionError(
                "Expect destination to be an analysis object")

        parent_id = destination.parents.get('project')  # type: ignore
        if not parent_id:
            raise GearExecutionError(
                f'Cannot find parent project for: {destination.id}'  # type: ignore
            )
        fw_project = proxy.get_project_by_id(parent_id)  # type: ignore
        if not fw_project:
            raise GearExecutionError("Destination project not found")

        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        return AttributeCuratorVisitor(client=client,
                                       project=project,
                                       derive_rules=derive_rules,
                                       filename_pattern=filename_pattern)

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group,
                 self.__project.label)

        deriver = AttributeDeriver(rules_file=Path(
                                       self.__derive_rules.filepath))

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                date_key=self.__date_key,
                filename_pattern=self.__filename_pattern)
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(context=context,
            deriver=deriver,
            scheduler=scheduler)


def main():
    """Main method for Attribute Curator."""
    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
