"""Entry script for REDCap Project Info Management."""

import logging
from pathlib import Path
from typing import List, Optional

from centers.center_group import REDCapProjectInput
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream
from pydantic import ValidationError

from redcap_info_app.main import run

log = logging.getLogger(__name__)


class REDCapProjectInfoVisitor(GearExecutionEnvironment):
    """Visitor for the REDCap Project Info Management gear."""

    def __init__(self, admin_id: str, client: ClientWrapper, input_filepath: Path):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__input_file_path = input_filepath

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "REDCapProjectInfoVisitor":
        """Visit context to accumulate inputs for the gear.

        Args:
            context: The gear context.
        """
        client = ContextClient.create(context=context)
        input_file_path = context.config.get_input_path("input_file")
        if not input_file_path:
            raise GearExecutionError("No input file provided")

        return REDCapProjectInfoVisitor(
            admin_id=context.config.opts.get("admin_group", "nacc"),
            client=client,
            input_filepath=input_file_path,
        )

    def run(self, context: GearContext) -> None:
        """Run the REDCap Project Info Management gear.

        Args:
            context: the gear execution context
        """
        project_list = self.__get_project_list(self.__input_file_path)
        run(
            project_list=project_list,
            admin_group=self.admin_group(admin_id=self.__admin_id),
        )

    # pylint: disable=no-self-use
    def __get_project_list(self, input_file_path: Path) -> List[REDCapProjectInput]:
        """Get the REDCap project info objects from the input file.

        Args:
            input_file_path: The path to the input file.
        Returns:
            A list of REDCap project info objects.
        """
        try:
            with input_file_path.open("r", encoding="utf-8 ") as input_file:
                object_list = load_from_stream(input_file)
        except YAMLReadError as error:
            raise GearExecutionError(
                f"No REDCap project info read from input: {error}"
            ) from error
        if not object_list:
            raise GearExecutionError("No REDCap project info read from input file")

        project_list = []
        for project_object in object_list:
            try:
                project_list.append(REDCapProjectInput.model_validate(project_object))
            except ValidationError as error:
                log.error("Invalid REDCap project info: %s", error)
                continue
        if not project_list:
            raise GearExecutionError(
                "No valid REDCap project info read from input file"
            )

        return project_list


def main():
    """Main method for REDCap Project Info Management."""

    GearEngine().run(gear_type=REDCapProjectInfoVisitor)


if __name__ == "__main__":
    main()
