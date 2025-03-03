"""Entry script for UDS Curator."""

import logging
from typing import Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore

from uds_curator_app.main import run

log = logging.getLogger(__name__)


class UDSCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(self, *, client: ClientWrapper, project: ProjectAdaptor):
        super().__init__(client=client)
        self.__project = project

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'UDSCuratorVisitor':
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

        project = ProjectAdaptor(project=fw_project,
                                 proxy=proxy)  # type: ignore

        return UDSCuratorVisitor(client=client,
                                 project=project)  # type: ignore

    def run(self, context: GearToolkitContext) -> None:
        log.info("Curating project: %s/%s", self.__project.group,
                 self.__project.label)
        run(context=context, project=self.__project)  # type: ignore


def main():
    """Main method for UDS Curator."""

    GearEngine().run(gear_type=UDSCuratorVisitor)


if __name__ == "__main__":
    main()
