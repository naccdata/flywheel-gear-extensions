"""Entry script for loni_csv_metadata_processor."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
)
from loni_csv_metadata_processor_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)


class loni_csv_metadata_processorVisitor(GearExecutionEnvironment):
    """Visitor for the loni_csv_metadata_processor gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'loni_csv_metadata_processorVisitor':
        """Creates a loni_csv_metadata_processor execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return loni_csv_metadata_processorVisitor(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for loni_csv_metadata_processor."""

    GearEngine().run(gear_type=loni_csv_metadata_processorVisitor)


if __name__ == "__main__":
    main()
