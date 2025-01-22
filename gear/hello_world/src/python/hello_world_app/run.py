"""Entry script for Hello World."""

import logging

from typing import Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper
)
from hello_world_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)

class HelloWorldVisitor(GearExecutionEnvironment):
    """Visitor for the Hello World gear."""

    def __init__(self,
                 client: ClientWrapper,
                 input_file: InputFileWrapper,
                 target_project_id: str,
                 output_filename: str,
                 local_run: bool = False):
        super().__init__(client=client)

        if local_run and not target_project_id:
            raise ValueError("If local run is set to true, a "
                             "target project ID must be provided")

        self.__input_file = input_file
        self.__target_project_id = target_project_id
        self.__output_filename = output_filename
        self.__local_run = local_run

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'HelloWorldVisitor':
        """Creates a HelloWorldVisitor object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)

        output_filename = context.config.get('output_filename', None)
        if not output_filename:
            raise GearExecutionError("Output filename not defined")

        input_file = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        target_project_id = context.config.get('target_project_id', None)
        local_run = context.config.get('local_run', False)

        return HelloWorldVisitor(
            client=client,
            input_file=input_file,
            target_project_id=target_project_id,
            output_filename=output_filename,
            local_run=local_run)

    def run(self, context: GearToolkitContext) -> None:
        """Run the Hello World gear."""

        # if target project ID is not set, try to grab it from the
        # input file's parent
        if not self.__target_project_id:
            try:
                file_id = self.__input_file.file_id
                file = self.proxy.get_file(file_id)
                project = file.parents.project
            except ApiException as error:
                raise GearExecutionError(
                    f'Failed to find the input file: {error}') from error
        else:
            project = self.proxy.get_project_by_id(self.__target_project_id)

        project = ProjectAdaptor(project=project, proxy=self.proxy)

        run(proxy=self.proxy,
            context=context,
            project=project,
            input_file=self.__input_file,
            output_filename=self.__output_filename,
            local_run=self.__local_run)


def main():
    """Main method for Hello World."""
    GearEngine().run(gear_type=HelloWorldVisitor)


if __name__ == "__main__":
    main()
