"""Entry script for csv_center_splitter."""
import logging
from typing import Optional

from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from outputs.errors import ListErrorWriter

from csv_center_splitter_app.main import run

log = logging.getLogger(__name__)


class CSVCenterSplitterVisitor(GearExecutionEnvironment):
    """Visitor for the CSV Center Splitter gear."""

    def __init__(self,
                 client: ClientWrapper,
                 file_input: InputFileWrapper,
                 adcid_key: str,
                 target_project: str,
                 staging_project_id: str = None,
                 allow_merged_cells: bool = False,
                 delimiter: str = ',',
                 local_run: bool = False):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__adcid_key = adcid_key
        self.__target_project = target_project
        self.__staging_project_id = staging_project_id
        self.__allow_merged_cells = allow_merged_cells
        self.__delimiter = delimiter
        self.__local_run = local_run

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'CSVCenterSplitterVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        target_project = context.config.get('target_project', None)
        staging_project_id = context.config.get('staging_project_id', None)

        if not (target_project or staging_project_id):
            raise GearExecutionError("No target or staging project provided")

        adcid_key = context.config.get('adcid_key', None)
        if not adcid_key:
            raise GearExecutionError("No ADCID key provided")

        allow_merged_cells = context.config.get('allow_merged_cells', False)
        delimiter = context.config.get('delimiter', ',')
        local_run = context.config.get('local_run', False)

        return CSVCenterSplitterVisitor(client=client,
                                        file_input=file_input,
                                        adcid_key=adcid_key,
                                        target_project=target_project,
                                        staging_project_id=staging_project_id,
                                        allow_merged_cells=allow_merged_cells,
                                        delimiter=delimiter,
                                        local_run=local_run)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the CSV Center Splitter app."""
        # if local run, give dummy container for local file, otherwise
        # grab from project
        if self.__local_run:
            file_id = 'local-container'
            fw_path = 'local-run'
        else:
            file_id = self.__file_input.file_id
            try:
                file = self.proxy.get_file(file_id)
                fw_path = self.proxy.get_lookup_path(file)
            except ApiException as error:
                raise GearExecutionError(
                    f'Failed to find the input file: {error}') from error

        with open(self.__file_input.filepath, mode='r', encoding='utf8') as fh:
            error_writer = ListErrorWriter(container_id=file_id,
                                           fw_path=fw_path)

            run(proxy=self.proxy,
                input_file=fh,
                input_filename=self.__file_input.filename,
                error_writer=error_writer,
                adcid_key=self.__adcid_key,
                target_project=self.__target_project,
                staging_project_id=self.__staging_project_id,
                allow_merged_cells=self.__allow_merged_cells,
                delimiter=self.__delimiter)


def main():
    """Main method for CsvCenterSplitter.

    Splits CSV and distributes per center.
    """

    GearEngine.create_with_parameter_store().run(
        gear_type=CSVCenterSplitterVisitor)


if __name__ == "__main__":
    main()
