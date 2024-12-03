"""Entry script for APOE Transformer."""

import logging
from pathlib import Path
from typing import Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
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
from outputs.errors import ListErrorWriter

from apoe_transformer_app.main import run

log = logging.getLogger(__name__)


class APOETransformerVisitor(GearExecutionEnvironment):
    """Visitor for the APOE Transformer gear."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 output_filename: str, target_project_id: str, local_run: bool,
                 delimiter: str):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__output_filename = output_filename
        self.__target_project_id = target_project_id
        self.__local_run = local_run
        self.__delimiter = delimiter

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'APOETransformerVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)
        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        target_project_id = context.config.get('target_project_id', None)
        local_run = context.config.get('local_run', False)

        if local_run and not target_project_id:
            raise GearExecutionError(
                "local_run set to True, target_project_id " +
                "must be provided.")

        output_filename = context.config.get('output_filename', None)
        if not output_filename:
            path = Path(file_input.filename)
            output_filename = str(
                path.with_stem(path.stem + "_apoe_transformed"))

        return APOETransformerVisitor(client=client,
                                      file_input=file_input,
                                      output_filename=output_filename,
                                      target_project_id=target_project_id,
                                      local_run=local_run,
                                      delimiter=context.config.get(
                                          'delimiter', ','))

    def run(self, context: GearToolkitContext) -> None:
        """Runs the APOE Transformer app."""
        if self.__local_run:
            file_id = 'local-container'
            fw_path = 'local-run'
        else:
            file_id = self.__file_input.file_id
            try:
                file = self.proxy.get_file(file_id)
                fw_path = self.proxy.get_lookup_path(file)
                target_project_id = file.parents.project
            except ApiException as error:
                raise GearExecutionError(
                    f'Failed to find the input file: {error}') from error

        if self.__target_project_id:
            target_project_id = self.__target_project_id
        else:
            log.info(
                "No target project ID provided, defaulting to input file's " +
                f"parent project: {target_project_id}")

        target_project = self.proxy.get_project_by_id(target_project_id)
        if not target_project:
            raise GearExecutionError(
                f'Did not find a project with ID {target_project_id}')

        project = ProjectAdaptor(project=target_project, proxy=self.proxy)
        with open(self.__file_input.filepath, mode='r', encoding='utf8') as fh:
            error_writer = ListErrorWriter(container_id=file_id,
                                           fw_path=fw_path)
            run(proxy=self.proxy,
                input_file=fh,
                output_filename=self.__output_filename,
                target_project=project,
                error_writer=error_writer,
                delimiter=self.__delimiter)


def main():
    """Main method for APOE Transformer."""
    GearEngine().run(gear_type=APOETransformerVisitor)


if __name__ == "__main__":
    main()
