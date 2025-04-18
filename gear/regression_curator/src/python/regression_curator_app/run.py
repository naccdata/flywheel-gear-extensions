"""Entry script for Regression Curator."""
import json
import logging

from typing import Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from outputs.errors import MPListErrorWriter

from regression_curator_app.main import run

log = logging.getLogger(__name__)


class RegressionCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the Regression Curator gear."""

    def __init__(self, client: ClientWrapper,
                 baseline_file: InputFileWrapper,
                 filename_pattern: str):
        super().__init__(client=client)
        self.__baseline_file = baseline_file
        self.__filename_pattern = filename_pattern

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'RegressionCuratorVisitor':
        """Creates a Regression Curator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        filename_pattern = context.config.get('filename_pattern', "*.json")

        # TODO: add option to generate QAF baseline from S3 file directly,
        # right now generated manually with an off-pipeline script
        baseline_file = InputFileWrapper.create(input_name='baseline',
                                                context=context)

        return RegressionCuratorVisitor(client=client,
                                        baseline_file=baseline_file,
                                        filename_pattern=filename_pattern)

    def run(self, context: GearToolkitContext) -> None:
        file_id = self.__file_input.file_id
        try:
            file = self.proxy.get_file(file_id)
            fw_path = self.proxy.get_lookup_path(file)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        error_writer = MPListErrorWriter(container_id=file_id,
                                         fw_path=fw_path)

        project = self.__file_input.get_parent_project(self.proxy)
        if not project:
            raise GearExecutionError(
                f'Could not grab parent project of {self.__file_input.filename}')

        try:
            scheduler = ProjectCurationScheduler.create(
                project=project,
                filename_pattern=self.__filename_pattern)
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        with open(self.__file_input.filepath, mode='r', encoding='utf-8') as fh:
            baseline = json.loads(fh)
            run(proxy=self.proxy,
                baseline=baseline,
                scheduler=scheduler,
                error_writer=error_writer)


def main():
    """Main method for Regression Curator."""

    GearEngine().run(gear_type=RegressionCuratorVisitor)


if __name__ == "__main__":
    main()
