"""Script to pull directory information and convert to file expected by the
user management gear."""
import logging
from typing import Dict, List, Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterError, ParameterStore
from redcap_api.redcap_connection import REDCapConnectionError, REDCapReportConnection
from yaml.representer import RepresenterError

from directory_app.main import run

log = logging.getLogger(__name__)


class DirectoryPullVisitor(GearExecutionEnvironment):
    """Defines the directory pull gear."""

    def __init__(self, client: ClientWrapper, user_filename: str,
                 user_report: List[Dict[str, str]]):
        super().__init__(client=client)
        self.__user_filename = user_filename
        self.__user_report = user_report

    @classmethod
    def create(
            cls, context: GearToolkitContext,
            parameter_store: Optional[ParameterStore]
    ) -> 'DirectoryPullVisitor':
        """Creates directory pull execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Returns:
          the DirectoryPullVisitor
        Raises:
          GearExecutionError if the config or parameter path are missing values
        """
        assert parameter_store, "Parameter store expected"

        client = ContextClient.create(context)
        param_path = context.config.get('parameter_path')
        if not param_path:
            raise GearExecutionError("No parameter path")

        try:
            report_parameters = parameter_store.get_redcap_report_parameters(
                param_path=param_path)
        except ParameterError as error:
            raise GearExecutionError(f'Parameter error: {error}') from error

        try:
            directory_proxy = REDCapReportConnection.create_from(
                report_parameters)
            user_report = directory_proxy.get_report_records()
        except REDCapConnectionError as error:
            raise GearExecutionError(
                f'Failed to pull users from directory: {error.message}'
            ) from error

        user_filename = context.config.get('user_file')
        if not user_filename:
            raise GearExecutionError("No user file name provided")

        return DirectoryPullVisitor(client=client,
                                    user_filename=user_filename,
                                    user_report=user_report)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the directory pull gear.

        Args:
            engine (GearExecutionEngine): The gear execution engine.
        """
        assert context, 'Gear context required'
        assert self.__user_filename, 'User filename required'

        if self.client.dry_run:
            log.info('Would write user entries to file %s on %s %s',
                     self.__user_filename, context.destination['type'],
                     context.destination['id'])
            return

        try:
            yaml_text = run(user_report=self.__user_report)
        except RepresenterError as error:
            raise GearExecutionError(
                "Error: can't create YAML for file"
                f"{self.__user_filename}: {error}") from error

        with context.open_output(self.__user_filename,
                                 mode='w',
                                 encoding='utf-8') as out_file:
            out_file.write(yaml_text)


def main() -> None:
    """Main method for directory pull.

    Expects information needed for access to the user access report from
    the NACC directory on REDCap, and api key for flywheel. These must
    be given as environment variables.
    """

    GearEngine.create_with_parameter_store().run(
        gear_type=DirectoryPullVisitor)


if __name__ == "__main__":
    main()
