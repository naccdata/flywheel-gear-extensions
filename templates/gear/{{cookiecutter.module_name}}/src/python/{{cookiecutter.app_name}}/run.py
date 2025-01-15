"""Entry script for {{cookiecutter.gear_name}}."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment
)
from {{cookiecutter.app_name}}.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)

class {{cookiecutter.class_name}}Visitor(GearExecutionEnvironment):
    """Visitor for the {{cookiecutter.gear_name}} gear."""

    def __init__(self, admin_id: str, client: ClientWrapper, new_only: bool):
        super().__init__(client=client, admin_id=admin_id)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
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
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        return {{cookiecutter.class_name}}Visitor(
            admin_id=context.config.get("admin_group", "nacc"),
            client=client,
            new_only=context.config.get("new_only", False))

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy,
            new_only=self.__new_only)

def main():
    """Main method for {{cookiecutter.gear_name}}."""

    GearEngine.create_with_parameter_store().run(
        gear_type={{cookiecutter.class_name}}Visitor)

if __name__ == "__main__":
    main()
