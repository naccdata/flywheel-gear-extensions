"""Entry script for UDS Curator."""

import logging
from typing import Optional

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

from attribute_curator_app.main import CurationType, run

log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(self, client: ClientWrapper, project: ProjectAdaptor,
                 derive_rules: InputFileWrapper, date_key: str,
                 filename_pattern: str, curation_type: CurationType):
        super().__init__(client=client)
        self.__project = project
        self.__derive_rules = derive_rules
        self.__date_key = date_key
        self.__filename_pattern = filename_pattern
        self.__curation_type = curation_type

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

        date_key = context.config.get('date_key', None)
        if not date_key:
            raise GearExecutionError("Date key required")

        filename_pattern = context.config.get('filename_pattern', "*.json")

        derive_rules = InputFileWrapper.create(input_name='derive_rules',
                                               context=context)
        if not derive_rules:
            raise GearExecutionError("Derive rules CSV required")

        fw_project = derive_rules.get_parent_project(proxy=proxy)

        if not fw_project:
            raise GearExecutionError("Destination project not found")

        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        try:
            curation_type = CurationType(
                context.config.get('curation_type', 'General'))
        except ValueError as error:
            raise GearExecutionError(error) from error

        return AttributeCuratorVisitor(client=client,
                                       project=project,
                                       derive_rules=derive_rules,
                                       date_key=date_key,
                                       filename_pattern=filename_pattern,
                                       curation_type=curation_type)

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group,
                 self.__project.label)

        run(context=context,
            project=self.__project,
            derive_rules=self.__derive_rules,
            date_key=self.__date_key,
            filename_pattern=self.__filename_pattern,
            curation_type=self.__curation_type)


def main():
    """Main method for Attribute Curator."""
    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
