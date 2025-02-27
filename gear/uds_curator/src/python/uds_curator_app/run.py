"""Entry script for UDS Curator."""

import logging
from typing import Optional

from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.context.context import Container
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

    def __init__(self, client: ClientWrapper, destination: Container):
        super().__init__(client=client)
        self.__destination = destination

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
        try:
            destination = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error
        if destination.container_type != 'project':  # type: ignore
            raise GearExecutionError("Destination container must be a project")

        return UDSCuratorVisitor(client=client, destination=destination)

    def run(self, context: GearToolkitContext) -> None:
        proxy = self.__client.get_proxy()
        project = proxy.get_project_by_id(
            self.__destination.id)  # type: ignore

        run(context=context, project=project)  # type: ignore


def main():
    """Main method for UDS Curator."""

    GearEngine().run(gear_type=UDSCuratorVisitor)


if __name__ == "__main__":
    main()
