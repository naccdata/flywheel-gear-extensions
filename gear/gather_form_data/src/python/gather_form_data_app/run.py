"""Entry script for Gather Form Data."""

import logging
from csv import DictWriter
from pathlib import Path
from typing import Optional, get_args

from flywheel_gear_toolkit.context.context import GearToolkitContext
from gather_submission_status_app.status_request import RequestClusteringVisitor
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from keys.types import ModuleName
from outputs.error_writer import ListErrorWriter

log = logging.getLogger(__name__)


class GatherFormDataVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Form Data gear."""

    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        gear_name: str,
        project_names: list[str],
        include_derived: bool,
        modules: set[ModuleName],
        study_id: str,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__gear_name = gear_name
        self.__project_names: list[str] = project_names
        self.__include_derived = include_derived
        self.__modules = modules
        self.__study_id = study_id

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
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

        admin_id = context.config.get("admin_group", DefaultValues.NACC_GROUP_ID)
        project_names = context.config.get("project_names", "").split(",")
        include_derived = context.config.get("include_derived", False)
        modules = context.config.get("modules", "").split(",")
        unexpected_modules = [
            module for module in modules if module not in get_args(ModuleName)
        ]
        if unexpected_modules:
            log.warning("ignoring unexpected modules: %s", ",".join(unexpected_modules))

        study_id = context.config.get("study_id", "adrc")
        gear_name = context.manifest.get("name", "gather-submission-status")

        return GatherFormDataVisitor(
            client=client,
            file_input=file_input,
            admin_id=admin_id,
            gear_name=gear_name,
            project_names=project_names,
            include_derived=include_derived,
            modules={module for module in get_args(ModuleName) if module in modules},
            study_id=study_id,
        )
    
    def write_data(self, context: GearToolkitContext, filename: str, fieldnames: list[str]) -> None:
        with context.open_output(filename, mode="w", encoding="utf-8") as output_file:
            writer = DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()

    def run(self, context: GearToolkitContext) -> None:
        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as request_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )

            admin_group = self.admin_group(admin_id=self.__admin_id)
            clustering = RequestClusteringVisitor(
                admin_group=admin_group,
                study_id=self.__study_id,
                project_names=self.__project_names,
                error_writer=error_writer,
            )
            with context.open_output(
                self.__output_filename, mode="w", encoding="utf-8"
            ) as output_file:
                writer = DictWriter(output_file, fieldnames=self.__report_fieldnames)
                writer.writeheader()
                success = run(
                    input_file=request_file,
                    modules=self.__modules,
                    clustering_visitor=clustering,
                    file_visitor=self.__file_visitor,
                    writer=writer,
                    error_writer=error_writer,
                )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors().model_dump(by_alias=True),
            )

            context.metadata.add_file_tags(
                self.__file_input.file_input, tags=self.__gear_name
            )


def main():
    """Main method for Gather Form Data."""

    GearEngine().run(gear_type=GatherFormDataVisitor)


if __name__ == "__main__":
    main()
