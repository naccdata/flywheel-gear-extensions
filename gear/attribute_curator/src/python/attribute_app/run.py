"""Defines curation gear to run in user-facing projects; hiding curation
details from users."""

import logging
import sys
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
from inputs.parameter_store import ParameterStore
from utils.utils import parse_string_to_list

from .main import run, AttributeCurator

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class AttributeCuratorVisitor(GearExecutionEnvironment):

    def __init__(self,
                 client: ClientWrapper,
                 file_input: InputFileWrapper,
                 curation_schema_uri: str,
                 aggregation_containers: List[str],
                 apply_containers: List[str],
                 form_date_key: str) -> None:
        super().__init__(client=client)

        self.__file_input = file_input
        self.__curation_schema_uri = curation_schema_uri
        self.__aggregation_containers = aggregation_containers
        self.__apply_containers = apply_containers
        self.__form_date_key = form_date_key

    @classmethod
    def create(
        cls, context: GearToolkitContext,
        parameter_store: Optional[ParameterStore]
    ) -> 'AttributeCuratorVisitor':


        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)

        if not file_input:
            raise GearExecutionError("Missing input file")

        curation_schema_uri = context.config.get('curation_schema_uri', None)
        form_date_key = context.config.get('form_date_key', None)
        aggregation_containers = parse_string_to_list(
            context.config.get('aggregation_containers', ''))
        apply_containers = parse_string_to_list(
            context.config.get('apply_containers', ''))

        if not curation_schema_uri:
            raise GearExecutionError('Curation schema S3 URI not provided')

        return AttributeCuratorVisitor(client=client,
                                       file_input=file_input,
                                       curation_schema_uri=curation_schema_uri,
                                       aggregation_containers=aggregation_containers,
                                       apply_containers=apply_containers,
                                       form_date_key=form_date_key)

    def run(self, context: GearToolkitContext):
        """Run the attribute curation visitor."""

        curator = AttributeCurator(context,
                                   self.__curation_schema_uri,
                                   self.__form_date_key,
                                   self.__aggregation_containers,
                                   self.__apply_containers)

        run(proxy=self.proxy,
            curator=curator,
            file_input=self.__file_input)


def main():
    """Describe gear detail here."""

    GearEngine.create_with_parameter_store().run(
        gear_type=AttributeCuratorVisitor)


if __name__ == "__main__":
    main()
