"""Entry script for Delete Form Submission."""

import logging
from typing import Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore

from form_deletion_app.main import run

log = logging.getLogger(__name__)


class FormDeletionVisitor(GearExecutionEnvironment):
    """Visitor for the Delete Form Submission gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'FormDeletionVisitor':
        """Creates a Delete Form Submission execution visitor.

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

        request_file_input = InputFileWrapper.create(input_name="request_file",
                                                     context=context)
        assert request_file_input, "missing expected input, request_file"

        form_configs_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context)
        assert form_configs_input, "missing expected input, form_configs_file"

        return FormDeletionVisitor(client=client)

    def run(self, context: GearContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Delete Form Submission."""

    GearEngine().run(gear_type=FormDeletionVisitor)


if __name__ == "__main__":
    main()
