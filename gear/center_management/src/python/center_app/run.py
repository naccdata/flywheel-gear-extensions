"""Reads a YAML file with center info.

array of centers:
    center-id - the group ID of center
    adcid - the ADC ID used to code data
    name - name of center
    is-active - whether center is active, has users if True
"""
import logging
from typing import List, Optional

from centers.center_info import CenterInfo
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream

from center_app.main import run

log = logging.getLogger(__name__)


class CenterCreationVisitor(GearExecutionEnvironment):
    """Defines the center management gear."""

    def __init__(self,
                 admin_id: str,
                 client: ClientWrapper,
                 center_filepath: str,
                 new_only: bool = False):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__new_only = new_only
        self.__center_filepath = center_filepath

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'CenterCreationVisitor':
        """Creates a center creation execution visitor.

        Args:
          context: the gear context
        Returns:
          the center creation visitor
        Raises:
          GearExecutionError if the center file cannot be loaded
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        center_filepath = context.get_input_path('center_file')
        if not center_filepath:
            raise GearExecutionError('No center file provided')
        admin_id = context.config.get("admin_group", "nacc")

        return CenterCreationVisitor(admin_id=admin_id,
                                     client=client,
                                     center_filepath=center_filepath,
                                     new_only=context.config.get(
                                         "new_only", False))

    def __get_center_list(self, center_file_path: str) -> List[CenterInfo]:
        """Get the centers from the file.

        Args:
          center_file_path: the path to the center file.
        Returns:
          List of center objects
        """
        try:
            with open(center_file_path, 'r', encoding='utf-8') as center_file:
                object_list = load_from_stream(center_file)
        except YAMLReadError as error:
            raise GearExecutionError(
                f'No centers read from center file {center_file_path}: {error}'
            ) from error
        if not object_list:
            raise GearExecutionError('No centers found in center file')

        return [CenterInfo(**center_doc) for center_doc in object_list]

    def run(self, context: GearToolkitContext) -> None:
        """Executes the gear.

        Args:
            context: the gear execution context

        Raises:
            AssertionError: If admin group ID or center list is not provided.
        """
        run(proxy=self.proxy,
            admin_group=self.admin_group(admin_id=self.__admin_id),
            center_list=self.__get_center_list(self.__center_filepath),
            role_names=['curate', 'upload', 'gear-bot'],
            new_only=self.__new_only)


def main():
    """Main method to run the center creation gear."""

    GearEngine.create_with_parameter_store().run(
        gear_type=CenterCreationVisitor)


if __name__ == "__main__":
    main()
