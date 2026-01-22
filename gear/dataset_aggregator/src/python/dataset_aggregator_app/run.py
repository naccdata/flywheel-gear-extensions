"""Entry script for Dataset Aggregator."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from dataset_aggregator_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)


class DatasetAggregatorVisitor(GearExecutionEnvironment):
    """Visitor for the Dataset Aggregator gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'DatasetAggregatorVisitor':
        """Creates a Dataset Aggregator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return DatasetAggregatorVisitor(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Dataset Aggregator."""

    GearEngine().run(gear_type=DatasetAggregatorVisitor)


if __name__ == "__main__":
    main()
