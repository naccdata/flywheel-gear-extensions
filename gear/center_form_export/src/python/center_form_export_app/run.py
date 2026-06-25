"""Entry script for Center Form Export."""

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
from center_form_export_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)


class CenterFormExportVisitor(GearExecutionEnvironment):
    """Visitor for the Center Form Export gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'CenterFormExportVisitor':
        """Creates a Center Form Export execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return CenterFormExportVisitor(client=client)

    def run(self, context: GearContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Center Form Export."""

    GearEngine().run(gear_type=CenterFormExportVisitor)


if __name__ == "__main__":
    main()
