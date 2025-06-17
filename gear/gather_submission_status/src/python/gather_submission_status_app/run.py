"""Entry script for Gather Submission Status."""

import logging
from pathlib import Path
from typing import Optional

from flywheel_gear_toolkit.context.context import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from outputs.errors import ListErrorWriter

from gather_submission_status_app.main import run

log = logging.getLogger(__name__)


class GatherSubmissionStatusVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Submission Status gear."""

    def __init__(self, client: ClientWrapper, admin_id: str,
                 file_input: InputFileWrapper, output_filename: str,
                 gear_name: str):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__output_filename = output_filename
        self.__gear_name = gear_name

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'GatherSubmissionStatusVisitor':
        """Creates a Gather Submission Status execution visitor.

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
        file_input = InputFileWrapper.create(input_name="input_file",
                                             context=context)
        assert file_input, "create raises exception if missing input file"

        output_filename = context.config.get("output_file",
                                             "submission-status.csv")
        admin_id = context.config.get("admin_group",
                                      DefaultValues.NACC_GROUP_ID)
        gear_name = context.manifest.get("name", "gather-submission-status")
        return GatherSubmissionStatusVisitor(client=client,
                                             file_input=file_input,
                                             output_filename=output_filename,
                                             admin_id=admin_id,
                                             gear_name=gear_name)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the gather-submission-status app.

        Args:
          context: the gear execution context
        """

        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as csv_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(container_id=file_id,
                                           fw_path=self.proxy.get_lookup_path(
                                               self.proxy.get_file(file_id)))

            admin_group = self.admin_group(admin_id=self.__admin_id)
            with context.open_output(self.__output_filename,
                                     mode="w",
                                     encoding="utf-8") as status_file:
                success = run(proxy=self.proxy,
                              input_file=csv_file,
                              admin_group=admin_group,
                              error_writer=error_writer,
                              output_file=status_file)

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name="validation",
                                           state="PASS" if success else "FAIL",
                                           data=error_writer.errors())

            context.metadata.add_file_tags(self.__file_input.file_input,
                                           tags=self.__gear_name)


def main():
    """Main method for Gather Submission Status."""

    GearEngine().run(gear_type=GatherSubmissionStatusVisitor)


if __name__ == "__main__":
    main()
