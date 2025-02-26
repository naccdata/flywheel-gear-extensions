"""Entry script for UDS Curator."""

import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore

from uds_curator_app.main import run

log = logging.getLogger(__name__)


class UDSCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the UDS Curator gear."""

    def __init__(self, client: ClientWrapper, input_file: InputFileWrapper):
        super().__init__(client=client)
        self.__input_file = input_file

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
        input_file = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        assert input_file, "missing expected input, input_file"

        return UDSCuratorVisitor(client=client, input_file=input_file)

    def run(self, context: GearToolkitContext) -> None:
        run(context=context, input_file=self.__input_file.file_input)


def main():
    """Main method for UDS Curator."""

    GearEngine().run(gear_type=UDSCuratorVisitor)


if __name__ == "__main__":
    main()
