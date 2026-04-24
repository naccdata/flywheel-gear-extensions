"""Entry script for File Distribution."""

import csv
import io
import logging
import re
from typing import List, Optional

from flywheel import FileEntry
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
from nacc_common.field_names import FieldNames
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
        associated_csv_regex: Optional[str] = None,
        adcid_key: str = FieldNames.ADCID,
        batch_size: int = 8,
        downstream_gears: Optional[List[str]] = None,
        include: Optional[str] = None,
        exclude: Optional[str] = None,
    ):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__target_project = target_project
        self.__staging_project_id = staging_project_id
        self.__associated_csv_regex = associated_csv_regex
        self.__adcid_key = adcid_key
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
        associated_csv_regex = options.get("associated_csv_regex", None)
        adcid_key = options.get("adcid_key", FieldNames.ADCID)

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
                raise GearExecutionError(f"Invalid batch size: {batch_size}")

        except (TypeError, GearExecutionError) as e:
            raise GearExecutionError(
                f"Batch size must be a non-negative integer: {batch_size}"
            ) from e

        return FileDistributionVisitor(
            client=client,
            file_input=file_input,
            target_project=target_project,
            staging_project_id=staging_project_id,
            associated_csv_regex=associated_csv_regex,
            adcid_key=adcid_key,
            batch_size=batch_size,
            downstream_gears=downstream_gears,
            include=options.get("include", None),
            exclude=options.get("exclude", None),
        )

    def __find_associated_adcids(self, file: FileEntry) -> List[str]:
        """Find associated ADCIDs from associated file. Searches for a file
        matching the capture regex specified by the associated csv regex.

        Args:
            file: the input file we are distributing

        Returns:
            List of ADCIDs to distribute to, if applicable
        """
        if self.__staging_project_id:
            log.info("Staging project ID provided, will not iterate over ADCIDs")
            return []

        if not self.__associated_csv_regex:
            log.info("No associated CSV regex provided, will use full ADCID list")
            return self.__centers

        match = re.search(self.__associated_csv_regex, self.__file_input.filename)
        if not match:
            raise GearExecutionError(
                "Failed to execute regex on filename: "
                + f"{self.__associated_csv_regex} on {self.__file_input.filename}"
            )

        associated_filename = f"{match.group(1)}.csv"
        project = self.__file_input.get_parent_project(self.proxy, file=file)
        associated_csv = project.get_file(associated_filename)
        if not associated_csv:
            raise GearExecutionError(
                f"Could not find an associated fle called {associated_filename}"
            )

        log.info(f"Found associated CSV {associated_filename}, parsing for ADCID list")

        adcids = set()
        data = associated_csv.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))

        if not reader.fieldnames or self.__adcid_key not in reader.fieldnames:
            raise GearExecutionError(
                f"Column {self.__adcid_key} not found in {associated_filename}"
            )

        for row in reader:
            adcid = row[self.__adcid_key]
            if adcid:
                adcids.add(adcid)

        log.info(f"Found {len(adcids)} associated ADCIDs")
        return list(adcids)

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

        centers = self.__find_associated_adcids(file)

        run(
            proxy=self.proxy,
            error_writer=ListErrorWriter(container_id=file_id, fw_path=fw_path),
            file=file,
            centers=centers,
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
