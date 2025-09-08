"""Entry script for Gather Form Data."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
)
from gather_form_data_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)


class GatherFormDataVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Form Data gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'GatherFormDataVisitor':
        """Creates a Gather Form Data execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return GatherFormDataVisitor(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Gather Form Data."""

    GearEngine().run(gear_type=GatherFormDataVisitor)


if __name__ == "__main__":
    main()
