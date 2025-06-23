"""Entry script for csv_center_splitter."""

import logging
from typing import List, Optional, Set

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
from utils.utils import parse_string_to_list

from csv_center_splitter_app.main import run

log = logging.getLogger(__name__)


class CSVCenterSplitterVisitor(GearExecutionEnvironment):
    """Visitor for the CSV Center Splitter gear."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        adcid_key: str,
        target_project: str,
        include: Set[str],
        exclude: Set[str],
        batch_size: int,
        staging_project_id: Optional[str] = None,
        downstream_gears: Optional[List[str]] = None,
        delimiter: str = ",",
        local_run: bool = False,
    ):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__adcid_key = adcid_key
        self.__target_project = target_project
        self.__staging_project_id = staging_project_id
        self.__include = include
        self.__exclude = exclude
        self.__batch_size = batch_size
        self.__downstream_gears = downstream_gears
        self.__delimiter = delimiter
        self.__local_run = local_run

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "CSVCenterSplitterVisitor":
        """Creates a gear execution object.

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

        target_project = context.config.get("target_project", None)
        staging_project_id = context.config.get("staging_project_id", None)

        if not (target_project or staging_project_id):
            raise GearExecutionError("No target or staging project provided")

        adcid_key = context.config.get("adcid_key", None)
        if not adcid_key:
            raise GearExecutionError("No ADCID key provided")

        # for including/excluding
        include = set(parse_string_to_list(context.config.get("include", "")))
        exclude = set(parse_string_to_list(context.config.get("exclude", "")))
        if include and exclude and include.intersection(exclude):
            raise GearExecutionError("Include and exclude lists cannot overlap")

        # for scheduling
        batch_size = context.config.get("batch_size", 1)
        downstream_gears = parse_string_to_list(
            context.config.get("downstream_gears", "")
        )

        try:
            batch_size = int(batch_size) if batch_size else None
            if batch_size is None or batch_size <= 0:
                raise GearExecutionError()

        except (TypeError, GearExecutionError) as e:
            raise GearExecutionError(
                f"Batch size must be a non-negative integer: {batch_size}"
            ) from e

        delimiter = context.config.get("delimiter", ",")
        local_run = context.config.get("local_run", False)

        return CSVCenterSplitterVisitor(
            client=client,
            file_input=file_input,  # type: ignore
            adcid_key=adcid_key,
            target_project=target_project,
            staging_project_id=staging_project_id,
            include=include,
            exclude=exclude,
            batch_size=batch_size,
            downstream_gears=downstream_gears,
            delimiter=delimiter,
            local_run=local_run,
        )

    def run(self, context: GearToolkitContext) -> None:
        """Runs the CSV Center Splitter app."""
        # if local run, give dummy container for local file, otherwise
        # grab from project
        if self.__local_run:
            file_id = "local-container"
            fw_path = "local-run"
        else:
            file_id = self.__file_input.file_id
            try:
                file = self.proxy.get_file(file_id)
                fw_path = self.proxy.get_lookup_path(file)
            except ApiException as error:
                raise GearExecutionError(
                    f"Failed to find the input file: {error}"
                ) from error

        centers = {str(adcid) for adcid in self.admin_group("nacc").get_adcids()}
        if self.__include:
            centers = {adcid for adcid in centers if adcid in self.__include}
        if self.__exclude:
            centers = {adcid for adcid in centers if adcid not in self.__exclude}

        with open(self.__file_input.filepath, mode="r", encoding="utf-8-sig") as fh:
            error_writer = ListErrorWriter(container_id=file_id, fw_path=fw_path)

            run(
                proxy=self.proxy,
                input_file=fh,
                input_filename=self.__file_input.filename,
                error_writer=error_writer,
                adcid_key=self.__adcid_key,
                target_project=self.__target_project,
                batch_size=self.__batch_size,
                staging_project_id=self.__staging_project_id,
                downstream_gears=self.__downstream_gears,
                include=centers,
                delimiter=self.__delimiter,
            )


def main():
    """Main method for CsvCenterSplitter.

    Splits CSV and distributes per center.
    """

    GearEngine.create_with_parameter_store().run(gear_type=CSVCenterSplitterVisitor)


if __name__ == "__main__":
    main()
