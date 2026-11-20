"""Entry script for the MRI Reface gear."""

import logging
from pathlib import Path

from fw_gear import GearContext
from pydantic import ValidationError

from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from mri_reface_app.main import RefaceConfig, RefaceError, run

log = logging.getLogger(__name__)


class MRIRefaceVisitor(GearExecutionEnvironment):
    """Visitor for the MRI Reface gear."""

    def __init__(
        self,
        client: ClientWrapper,
        *,
        file_input: InputFileWrapper,
        config: RefaceConfig,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__config = config

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: ParameterStore | None = None,
    ) -> "MRIRefaceVisitor":
        """Creates an MRI Reface execution visitor.

        Raises:
            GearExecutionError if the input file is missing or config is invalid
        """
        client = ContextClient.create(context=context)

        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        if not file_input:
            raise GearExecutionError("Missing expected input, input_file")

        try:
            config = RefaceConfig.model_validate(context.config.opts)
        except ValidationError as error:
            raise GearExecutionError(f"Invalid gear config: {error}") from error

        return MRIRefaceVisitor(client=client, file_input=file_input, config=config)

    def run(self, context: GearContext) -> None:
        """Runs mri_reface on the input file."""
        log.info("Input: %s", self.__file_input.filename)
        try:
            run(
                input_path=Path(self.__file_input.filepath),
                work_dir=Path(context.work_dir),
                output_dir=Path(context.output_dir),
                config=self.__config,
            )
        except RefaceError as error:
            raise GearExecutionError(str(error)) from error


def main():
    """Main method for MRI Reface."""
    GearEngine().run(gear_type=MRIRefaceVisitor)


if __name__ == "__main__":
    main()
