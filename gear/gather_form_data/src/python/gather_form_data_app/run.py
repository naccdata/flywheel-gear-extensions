"""Entry script for Gather Form Data."""

import logging
from datetime import date
from pathlib import Path
from typing import Optional, get_args

from data_requests.data_request import DataRequestVisitor, ModuleDataGatherer
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from outputs.error_writer import ListErrorWriter

from gather_form_data_app.main import run

ModuleName = str

log = logging.getLogger(__name__)


class GatherFormDataVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Form Data gear."""

    def __init__(
        self,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        project_names: list[str],
        info_paths: list[str],
        modules: set[ModuleName],
        study_id: str,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__project_names: list[str] = project_names
        self.__info_paths = info_paths
        self.__modules = modules
        self.__study_id = study_id

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "GatherFormDataVisitor":
        """Creates a Gather Form Data execution visitor.

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
        assert file_input, "create raises exception if missing input file"

        options = context.config.opts
        project_names = options.get("project_names", "").split(",")
        include_derived = options.get("include_derived", False)
        info_paths = ["forms.json", "derived"] if include_derived else ["forms.json"]
        modules = options.get("modules", "").split(",")
        unexpected_modules = [
            module for module in modules if module not in get_args(ModuleName)
        ]
        if unexpected_modules:
            log.warning("ignoring unexpected modules: %s", ",".join(unexpected_modules))

        study_id = options.get("study_id", "adrc")

        return GatherFormDataVisitor(
            client=client,
            file_input=file_input,
            project_names=project_names,
            info_paths=info_paths,
            modules={module for module in get_args(ModuleName) if module in modules},
            study_id=study_id,
        )

    def run(self, context: GearContext) -> None:
        data_gatherers: list[ModuleDataGatherer] = []
        for module_name in self.__modules:
            data_gatherers.append(
                ModuleDataGatherer(
                    proxy=self.proxy,
                    module_name=module_name,
                    info_paths=self.__info_paths,
                )
            )

        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as request_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )
            request_visitor = DataRequestVisitor(
                proxy=self.proxy,
                study_id=self.__study_id,
                project_names=self.__project_names,
                gatherers=data_gatherers,
                error_writer=error_writer,
            )

            success = run(
                request_file=request_file,
                request_visitor=request_visitor,
                error_writer=error_writer,
            )
            if success:
                self.__write_output(context, request_visitor.gatherers)

        context.metadata.add_qc_result(
            self.__file_input.file_input,
            name="validation",
            state="PASS" if success else "FAIL",
            data=error_writer.errors().model_dump(by_alias=True),
        )

        gear_name = self.get_gear_name(context, "gather-submission-status")
        context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)

    def __write_output(self, context: GearContext, gatherers: list[ModuleDataGatherer]):
        """Using the gear context, writes the data content in each gatherer to
        a file named with the study-id and the module of the gatherer.

        Args:
          context: the gear context
          gatherers: a list of ModuleDataGatherer objects
        """
        today = date.today().isoformat()
        for gatherer in gatherers:
            if not gatherer.content:
                log.warning(
                    "skipping output for module %s: no data found", gatherer.module_name
                )
                continue

            output_filename = f"{self.__study_id}-{gatherer.module_name}-{today}.csv"
            with context.open_output(
                output_filename, mode="w", encoding="utf-8"
            ) as output_file:
                # TODO: manage write errors
                output_file.write(gatherer.content)


def main():
    """Main method for Gather Form Data."""

    GearEngine().create_with_parameter_store().run(gear_type=GatherFormDataVisitor)


if __name__ == "__main__":
    main()
