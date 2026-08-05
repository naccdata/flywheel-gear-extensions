"""Entry script for REDCap image form importer."""

import logging
import sys
from typing import Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterStore
from redcap_api.redcap_connection import REDCapConnection
from redcap_api.redcap_parameter_store import REDCapParameters

from redcap_image_form_importer_app.main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class REDCapimageformimporterVisitor(GearExecutionEnvironment):
    """Visitor for the REDCap image form importer gear."""

    def __init__(
        self,
        dry_run: bool,
        client: ClientWrapper,
        parameter_store: ParameterStore,
        parameter_path: str,
    ):
        super().__init__(client=client)
        self.__dry_run = dry_run
        self.__param_store = parameter_store
        self.__parameter_path = parameter_path

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore] = None
    ) -> "REDCapimageformimporterVisitor":
        """Creates a REDCap image form importer execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        try:
            dry_run: bool = get_config(gear_context=context, key="dry_run")
            parameter_path: str = get_config(gear_context=context, key="parameter_path")
        except ConfigParseError as error:
            raise GearExecutionError(
                f"Incomplete configuration: {error.message}"
            ) from error

        client = ContextClient.create(context=context)

        return REDCapimageformimporterVisitor(
            dry_run=dry_run,
            client=client,
            parameter_store=parameter_store,
            parameter_path=parameter_path,
        )

    def run(self, context: GearContext) -> None:
        if context.config.destination["type"] == "session":
            session_id = context.config.destination["id"]
        elif context.config.destination["type"] == "acquisition":
            session_id = self.proxy.get_container_by_id(
                context.config.destination["id"]
            ).parents["session"]
        else:
            raise GearExecutionError(
                "Expected to run on associated session, given "
                f"{context.config.destination['type']}"
            )

        redcap_con = REDCapConnection.create_from(
            self.__param_store.get_parameters(
                param_type=REDCapParameters, parameter_path=self.__parameter_path
            )
        )

        run(
            dry_run=self.__dry_run,
            session_id=session_id,
            redcap_con=redcap_con,
            proxy=self.proxy,
            output_dir=str(context.output_dir),
        )


def main():
    """Main method for REDCap image form importer."""
    GearEngine().create_with_parameter_store().run(
        gear_type=REDCapimageformimporterVisitor
    )


if __name__ == "__main__":
    main()
