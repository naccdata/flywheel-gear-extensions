"""Entry script for {{cookiecutter.gear_name}}."""

import logging

from typing import Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from {{cookiecutter.app_name}}.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)


class {{cookiecutter.class_name}}Visitor(GearExecutionEnvironment):
    """Visitor for the {{cookiecutter.gear_name}} gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> '{{cookiecutter.class_name}}Visitor':
        """Creates a {{cookiecutter.gear_name}} execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return {{cookiecutter.class_name}}Visitor(client=client)

    def run(self, context: GearContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for {{cookiecutter.gear_name}}."""

    GearEngine().run(gear_type={{cookiecutter.class_name}}Visitor)


if __name__ == "__main__":
    main()
