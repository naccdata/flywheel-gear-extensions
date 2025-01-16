"""Entry script for Legacy Sanity Check."""

import logging

from typing import Optional

from datastore.forms_store import FormsStoreGeneric
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
)
from legacy_sanity_check_app.main import (
    LegacySanityChecker,
    run,
)
from inputs.parameter_store import ParameterStore
from outputs.errors import ListErrorWriter
from preprocess.preprocessor import FormProjectConfigs
from pydantic import ValidationError

log = logging.getLogger(__name__)

class LegacySanityCheckVisitor(GearExecutionEnvironment):
    """Visitor for the Legacy Sanity Check gear."""

    def __init__(self,
                 file_input: InputFileWrapper,
                 form_configs_input: InputFileWrapper):
        super().__init__(client=client, admin_id=admin_id)

        self.__file_input = file_input
        self.__form_configs_input = form_configs_input

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'LegacySanityCheckVisitor':
        """Creates a Legacy Sanity Check execution visitor.

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

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        assert file_input, "missing expected input, input_file"

        form_configs_input = InputFileWrapper.create(
            input_name='form_configs_file', context=context)
        assert form_configs_input, "missing expected input, form_configs_file"

        return LegacySanityCheckVisitor(
            file_input=file_input,
            form_configs_input=form_configs_input)

    def run(self, context: GearToolkitContext) -> None:
        """Run the Legacy Sanity Checker"""
        file_id = self.__file_input.file_id
        try:
            file = proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        project = self.__file_input.get_parent_project(
            self.proxy, file=file)

        error_writer = ListErrorWriter(
            container_id=file_id,
            fw_path=self.proxy.get_lookup_path(file))

        form_configs = None
        with open(self.__form_configs_input.filepath, mode='r') as fh:
            form_configs = None
            try:
                form_configs = FormProjectConfigs.model_validate_json(
                    fh.read())
            except ValidationError as error:
                raise GearExecutionError(
                    'Error reading form configurations file'
                    f'{self.__form_configs_input.filename}: {error}') from error

        sanity_checker = LegacySanityChecker(
            form_store=FormsStoreGeneric(project=project),
            form_configs=form_configs,
            error_writer=error_writer)

        run(proxy=self.proxy,
            sanity_checker=sanity_checker,
            project=project)

        # TODO: WRITE ERRORS TO LOG FILE

def main():
    """Main method for Legacy Sanity Check."""

    GearEngine.create_with_parameter_store().run(
        gear_type=LegacySanityCheckVisitor)

if __name__ == "__main__":
    main()
