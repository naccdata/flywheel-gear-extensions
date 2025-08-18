"""Entry script for Manage Participant Transfer."""

import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
)
from inputs.parameter_store import ParameterStore

from participant_transfer_app.main import run

log = logging.getLogger(__name__)


class ParticipantTransferVisitor(GearExecutionEnvironment):
    """Visitor for the Manage Participant Transfer gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "ParticipantTransferVisitor":
        """Creates a Manage Participant Transfer execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        return ParticipantTransferVisitor(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Manage Participant Transfer."""

    GearEngine.create_with_parameter_store().run(gear_type=ParticipantTransferVisitor)


if __name__ == "__main__":
    main()
