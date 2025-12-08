"""Entry script for Submission Logger."""

import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
)
from inputs.parameter_store import ParameterStore

from submission_logger_app.main import run

log = logging.getLogger(__name__)


class SubmissionLoggerVisitor(GearExecutionEnvironment):
    """Visitor for the Submission Logger gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "SubmissionLoggerVisitor":
        """Creates a Submission Logger execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return SubmissionLoggerVisitor(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Submission Logger."""

    GearEngine().run(gear_type=SubmissionLoggerVisitor)


if __name__ == "__main__":
    main()
