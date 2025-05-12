"""Entry script for Form Screening."""
import logging
import time
from typing import List, Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from gear_execution.gear_trigger import GearInfo
from inputs.parameter_store import ParameterStore
from utils.utils import parse_string_to_list

from form_screening_app.main import FormSchedulerGearConfigs, run

log = logging.getLogger(__name__)


class FormScreeningVisitor(GearExecutionEnvironment):
    """Visitor for the Form Screening gear."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 accepted_modules: List[str], queue_tags: List[str],
                 scheduler_gear: GearInfo):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__accepted_modules = accepted_modules
        self.__queue_tags = queue_tags
        self.__scheduler_gear = scheduler_gear

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'FormScreeningVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        if not file_input:
            raise GearExecutionError(
                "Gear config input_file not specified or not found")

        gear_name = context.manifest.get('name', 'form-screening')

        # We save the formatted file with same name as input file
        # To prevent gear rules running into a loop check whether the file is screened
        # Check the file origin to identify whether the file is updated by a gear job
        file_entry = file_input.file_entry(context=context)
        if file_entry.origin.type != 'user':
            time.sleep(30)
            file_entry = file_entry.reload()
            if gear_name in file_entry.tags:
                log.info("Input file %s already screened and formatted",
                         file_entry.name)
            exit(0)

        config_file_path = context.get_input_path(
            'scheduler_gear_configs_file')

        accepted_modules = parse_string_to_list(
            context.config.get('accepted_modules', None))
        queue_tags = parse_string_to_list(context.config.get(
            'queue_tags', None),
                                          to_lower=False)

        if not accepted_modules:
            raise GearExecutionError("No accepted modules provided")
        if not queue_tags:
            raise GearExecutionError("No tags to add provided")
        if not config_file_path:
            raise GearExecutionError("No scheduler gear config file specified")

        scheduler_gear = GearInfo.load_from_file(
            config_file_path, configs_class=FormSchedulerGearConfigs)
        if not scheduler_gear:
            raise GearExecutionError(
                f'Error(s) in reading scheduler gear configs file - {config_file_path}'
            )

        return FormScreeningVisitor(
            client=client,
            file_input=file_input,  # type: ignore
            accepted_modules=accepted_modules,
            queue_tags=queue_tags,
            scheduler_gear=scheduler_gear)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the Form Screening app."""

        run(proxy=self.proxy,
            context=context,
            file_input=self.__file_input,
            accepted_modules=self.__accepted_modules,
            queue_tags=self.__queue_tags,
            scheduler_gear=self.__scheduler_gear)


def main():
    """Main method for FormScreeningVisitor.

    Screens the input file and queue for processing.
    """

    GearEngine.create_with_parameter_store().run(
        gear_type=FormScreeningVisitor)


if __name__ == "__main__":
    main()
