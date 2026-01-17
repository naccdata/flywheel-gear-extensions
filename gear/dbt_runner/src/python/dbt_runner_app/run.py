"""Entry script for DBT Runner."""

import logging
from typing import Any, Dict, List, Optional

from flywheel_gear_toolkit import GearToolkitContext
from fw_dataset.admin.dataset_builder import DatasetLoader
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.context_parser import get_api_key
from inputs.parameter_store import ParameterStore

from .main import run
from .storage_configs import (
    MultiStorageConfigs,
    SingleStorageConfigs,
)

log = logging.getLogger(__name__)


class DBTRunnerVisitor(GearExecutionEnvironment):
    """Visitor for the DBT Runner gear."""

    def __init__(
        self,
        client: ClientWrapper,
        dbt_project_zip: InputFileWrapper,
        storage_label: str,
        output_prefix: str,
        source_prefix: Optional[str] = None,
        target_project: Optional[str] = None,
    ):
        super().__init__(client=client)
        self.__dbt_project_zip = dbt_project_zip
        self.__storage_label = storage_label
        self.__output_prefix = output_prefix
        self.__source_prefix = source_prefix
        self.__target_project = target_project

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
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

        debug = context.config.get("debug", False)
        if debug:
            log.setLevel(logging.DEBUG)
            log.info("Set logging level to DEBUG")

        storage_label = context.config.get("storage_label", None)
        output_prefix = context.config.get("output_prefix", None)
        source_prefix = context.config.get("source_prefix", None)
        target_project = context.config.get("target_project", None)

        if not storage_label:
            raise GearExecutionError("storage_label required")
        if not output_prefix:
            raise GearExecutionError("output_prefix required")
        if (not source_prefix and not target_project) or (
            source_prefix and target_project
        ):
            raise GearExecutionError(
                "Exactly one of source_prefix or target_project required"
            )

        return DBTRunnerVisitor(
            client=client,
            dbt_project_zip=dbt_project_zip,
            storage_label=storage_label,
            output_prefix=output_prefix,
            source_prefix=source_prefix,
            target_project=target_project,
        )

    def __get_source_prefixes(
        self, api_key: str, context: GearToolkitContext
    ) -> List[str]:
        """Create source prefixes from center map by looking up which centers
        have the specified target project.

        Args:
            api_key: The FW API key; needed to create DatasetLoader
            context: The context to grab center map filtering
                arguments from

        Returns:
            List of found prefixes
        """
        center_ids = self.get_center_ids(context)
        source_prefixes: List[str] = []

        for center in center_ids:
            project = self.proxy.lookup(f"{center}/{self.__target_project}")
            if not project:
                log.warning(
                    f"No {self.__target_project} project found for "
                    + f"center {center}, skipping"
                )
                continue

            dataset_loader = DatasetLoader(api_key=api_key)
            dataset = dataset_loader.load_dataset(project.id)
            latest_dataset = dataset.get_latest_version()
            if not latest_dataset:
                log.warning(
                    f"No dataset found in {self.__target_project} project for "
                    + f"center {center}, skipping"
                )
                continue

            # build prefix from the latest dataset version
            instance = "TODO"  # way to query this from client?
            source_prefixes.append(
                f"{instance}/{center}/{project.id}/versions/{latest_dataset['version']}"
            )

        return source_prefixes

    def run(self, context: GearToolkitContext) -> None:
        api_key = get_api_key(context)
        if not api_key:
            raise GearExecutionError("API key not found")

        storage_args: Dict[str, Any] = {
            "storage_label": self.__storage_label,
            "output_prefix": self.__output_prefix,
        }

        if self.__source_prefix:
            storage_args["source_prefix"] = self.__source_prefix
            storage_class = SingleStorageConfigs
        else:
            storage_args["source_prefixes"] = self.__get_source_prefixes(
                api_key, context
            )
            storage_class = MultiStorageConfigs

        run(
            context=context,
            api_key=api_key,
            dbt_project_zip=self.__dbt_project_zip,
            storage_configs=storage_class(**storage_args),
        )


def main():
    """Main method for DBT Runner."""

    GearEngine.create_with_parameter_store().run(gear_type=DBTRunnerVisitor)


if __name__ == "__main__":
    main()
