"""Entry script for csv_center_splitter."""

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
from notifications.email_list import (
    EmailListClient,
    EmailListError,
    get_redcap_email_list_client,
)
from outputs.error_writer import ListErrorWriter
from utils.utils import (
    filter_include_exclude,
    parse_string_to_list,
)

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
        batch_size: int,
        target_project: Optional[str] = None,
        staging_project_id: Optional[str] = None,
        downstream_gears: Optional[List[str]] = None,
        include: Optional[str] = None,
        exclude: Optional[str] = None,
        delimiter: str = ",",
        local_run: bool = False,
        email_client: Optional[EmailListClient] = None,
    ):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__adcid_key = adcid_key
        self.__target_project = target_project
        self.__staging_project_id = staging_project_id
        self.__batch_size = batch_size
        self.__downstream_gears = downstream_gears
        self.__delimiter = delimiter
        self.__local_run = local_run
        self.__email_client = email_client

        self.__centers = filter_include_exclude(
            [str(x) for x in self.admin_group("nacc").get_adcids()], include, exclude
        )

    @classmethod
    def create(
        cls,
        context: GearContext,
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

        options = context.config.opts
        target_project = options.get("target_project", None)
        staging_project_id = options.get("staging_project_id", None)

        if not target_project and not staging_project_id:
            raise GearExecutionError(
                "One of target_project or staging_project_id must be provided"
            )

        adcid_key = options.get("adcid_key", None)
        if not adcid_key:
            raise GearExecutionError("No ADCID key provided")

        # for scheduling
        batch_size = options.get("batch_size", 1)
        downstream_gears = parse_string_to_list(options.get("downstream_gears", ""))

        try:
            batch_size = int(batch_size) if batch_size else None
            if batch_size is None or batch_size <= 0:
                raise GearExecutionError()

        except (TypeError, GearExecutionError) as e:
            raise GearExecutionError(
                f"Batch size must be a non-negative integer: {batch_size}"
            ) from e

        # for emails
        redcap_email_configs_file = InputFileWrapper.create(
            input_name="redcap_email_configs", context=context
        )
        try:
            email_client = get_redcap_email_list_client(
                redcap_email_configs_file=redcap_email_configs_file,
                parameter_store=parameter_store,
                dry_run=client.dry_run,
            )
        except EmailListError as e:
            raise GearExecutionError(e) from e

        return CSVCenterSplitterVisitor(
            client=client,
            file_input=file_input,  # type: ignore
            adcid_key=adcid_key,
            batch_size=batch_size,
            target_project=target_project,
            staging_project_id=staging_project_id,
            downstream_gears=downstream_gears,
            include=options.get("include", None),
            exclude=options.get("exclude", None),
            delimiter=options.get("delimiter", ","),
            local_run=options.get("local_run", False),
            email_client=email_client,
        )

    def run(self, context: GearContext) -> None:
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

        with open(self.__file_input.filepath, mode="r", encoding="utf-8-sig") as fh:
            error_writer = ListErrorWriter(container_id=file_id, fw_path=fw_path)

            run(
                proxy=self.proxy,
                input_file=fh,
                input_filename=self.__file_input.filename,
                error_writer=error_writer,
                adcid_key=self.__adcid_key,
                batch_size=self.__batch_size,
                target_project=self.__target_project,
                staging_project_id=self.__staging_project_id,
                downstream_gears=self.__downstream_gears,
                include=set(self.__centers),
                delimiter=self.__delimiter,
            )

        if self.__email_client:
            self.__email_client.send_emails()


def main():
    """Main method for CsvCenterSplitter.

    Splits CSV and distributes per center.
    """

    GearEngine.create_with_parameter_store().run(gear_type=CSVCenterSplitterVisitor)


if __name__ == "__main__":
    main()
