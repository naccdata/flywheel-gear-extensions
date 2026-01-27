"""Entry script for DBT Runner."""

import logging
from typing import Optional

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

from dbt_runner_app.main import StorageConfigs, run

log = logging.getLogger(__name__)


class DBTRunnerVisitor(GearExecutionEnvironment):
    """Visitor for the DBT Runner gear."""

    def __init__(
        self,
        client: ClientWrapper,
        dbt_project_zip: InputFileWrapper,
        storage_configs: StorageConfigs,
    ):
        super().__init__(client=client)
        self.__dbt_project_zip = dbt_project_zip
        self.__storage_configs = storage_configs

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "DBTRunnerVisitor":
        """Creates a DBT Runner execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        dbt_project_zip = InputFileWrapper.create(
            input_name="dbt_project_zip", context=context
        )

        if not dbt_project_zip:
            raise GearExecutionError("DBT project zip required")

        storage_configs = StorageConfigs(
            storage_label=context.config.opts.get("storage_label", None),
            source_prefix=context.config.opts.get("source_prefix", None),
            output_prefix=context.config.opts.get("output_prefix", None),
        )

        debug = context.config.opts.get("debug", False)
        if debug:
            log.setLevel(logging.DEBUG)
            log.info("Set logging level to DEBUG")

        return DBTRunnerVisitor(
            client=client,
            dbt_project_zip=dbt_project_zip,
            storage_configs=storage_configs,
        )

    def run(self, context: GearContext) -> None:
        run(
            context=context,
            client=self.client,
            dbt_project_zip=self.__dbt_project_zip,
            storage_configs=self.__storage_configs,
        )


def main():
    """Main method for DBT Runner."""

    GearEngine.create_with_parameter_store().run(gear_type=DBTRunnerVisitor)


if __name__ == "__main__":
    main()
