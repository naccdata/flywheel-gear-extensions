"""Entry script for Legacy Sanity Check."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
)
from legacy_sanity_check_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)

class LegacySanityCheckVisitor(GearExecutionEnvironment):
    """Visitor for the Legacy Sanity Check gear."""

    def __init__(self, admin_id: str, client: ClientWrapper, new_only: bool):
        super().__init__(client=client, admin_id=admin_id)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'LegacySanityCheckVisitor':
        """Creates a Legacy Sanity Check execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        return LegacySanityCheckVisitor(
            admin_id=context.config.get("admin_group", "nacc"),
            client=client,
            new_only=context.config.get("new_only", False))

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy,
            new_only=self.__new_only)

def main():
    """Main method for Legacy Sanity Check."""

    GearEngine.create_with_parameter_store().run(
        gear_type=LegacySanityCheckVisitor)

if __name__ == "__main__":
    main()
