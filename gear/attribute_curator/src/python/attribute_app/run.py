"""Defines curation gear to run in user-facing projects; hiding curation
details from users."""

import logging
import sys
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

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):
    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper) -> None:
        self.__client = client
        self.__file_input = file_input

    @classmethod
    def create(
        cls, context: GearToolkitContext, parameter_store: Optional[ParameterStore]
    ) -> "AttributeCuratorVisitor":
        client = ContextClient.create(context=context)
        file_input = InputFileWrapper.create(
            input_name="attribute_file", context=context
        )
        assert file_input, "attribute file is expected input"

        return AttributeCuratorVisitor(client=client, file_input=file_input)

    def run(self, context: GearToolkitContext):
        pass


def main():
    """Describe gear detail here."""

    GearEngine().run(gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
