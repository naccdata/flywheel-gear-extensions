"""Entry script for File Distribution."""

import logging
from typing import List, Optional

from flywheel.rest import ApiException
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from outputs.error_writer import ListErrorWriter
from utils.utils import (
    filter_include_exclude,
    parse_string_to_list,
)

from file_distribution_app.main import run

log = logging.getLogger(__name__)


class FileDistributionVisitor(GearExecutionEnvironment):
    """Visitor for the File Distribution gear."""

    def __init__(
        self,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        target_project: Optional[str] = None,
        staging_project_id: Optional[str] = None,
        batch_size: int = 8,
        downstream_gears: Optional[List[str]] = None,
        include: Optional[str] = None,
        exclude: Optional[str] = None,
    ):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__target_project = target_project
        self.__staging_project_id = staging_project_id
        self.__include = include
        self.__exclude = exclude
        self.__batch_size = batch_size
        self.__downstream_gears = downstream_gears

        self.__centers = filter_include_exclude(
            [str(x) for x in self.admin_group("nacc").get_adcids()], include, exclude
        )

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "FileDistributionVisitor":
        """Creates a File Distribution execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        if not file_input:
            raise GearExecutionError("No input file provided")

        options = context.config.opts
        target_project = options.get("target_project", None)
        staging_project_id = options.get("staging_project_id", None)

        if not target_project and not staging_project_id:
            raise GearExecutionError(
                "One of target_project or staging_project_id must be provided"
            )

        # for scheduling
        batch_size = options.get("batch_size", 8)
        downstream_gears = parse_string_to_list(options.get("downstream_gears", ""))

        try:
            batch_size = int(batch_size) if batch_size else None
            if batch_size is None or batch_size <= 0:
                raise GearExecutionError()

        except (TypeError, GearExecutionError) as e:
            raise GearExecutionError(
                f"Batch size must be a non-negative integer: {batch_size}"
            ) from e

        return FileDistributionVisitor(
            client=client,
            file_input=file_input,
            target_project=target_project,
            staging_project_id=staging_project_id,
            batch_size=batch_size,
            downstream_gears=downstream_gears,
            include=options.get("include", None),
            exclude=options.get("exclude", None),
        )

    def run(self, context: GearContext) -> None:
        """Runs the File Distribution app."""
        file_id = self.__file_input.file_id
        try:
            file = self.proxy.get_file(file_id)
            fw_path = self.proxy.get_lookup_path(file)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        run(
            proxy=self.proxy,
            error_writer=ListErrorWriter(container_id=file_id, fw_path=fw_path),
            file=file,
            centers=self.__centers,
            batch_size=self.__batch_size,
            target_project=self.__target_project,
            staging_project_id=self.__staging_project_id,
            downstream_gears=self.__downstream_gears,
        )


def main():
    """Main method for File Distribution."""

    GearEngine.create_with_parameter_store().run(gear_type=FileDistributionVisitor)


if __name__ == "__main__":
    main()
