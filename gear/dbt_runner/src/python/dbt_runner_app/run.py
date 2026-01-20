"""Entry script for DBT Runner."""

import logging
from typing import Dict, Optional

from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
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
from storage.storage import StorageManager

from .main import run
from .storage_handler import (
    MultiStorageHandler,
    SingleStorageHandler,
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
        self, storage_manager: StorageManager, context: GearToolkitContext
    ) -> Dict[str, str]:
        """Create source prefixes from center map by looking up which centers
        have the specified target project.

        Args:
            storage_manager: The StorageManager to aid with finding the
                latest prefix
            context: The context to grab center map filtering
                arguments from

        Returns:
            Mapping of center to its latest prefix
        """
        center_ids = self.get_center_ids(context)
        source_prefixes: Dict[str, str] = {}

        log.info(f"Looking up latest datasets under {storage_manager.storage_label}")

        for center in center_ids:
            try:
                project = self.proxy.lookup(f"{center}/{self.__target_project}")
            except ApiException:
                project = None

            if not project:
                log.warning(
                    f"No {self.__target_project} project found for "
                    + f"center {center}, skipping"
                )
                continue

            latest_dataset = storage_manager.get_latest_dataset_version(project)
            if not latest_dataset:
                continue

            source_prefixes[center] = latest_dataset

        if not source_prefixes:
            raise GearExecutionError(
                f"No datasets found for project {self.__target_project}"
            )

        return source_prefixes

    def run(self, context: GearToolkitContext) -> None:
        api_key = get_api_key(context)
        if not api_key:
            raise GearExecutionError("API key not found")

        log.info("=" * 80)
        log.info("dbt Runner Gear - Starting execution")
        log.info("=" * 80)

        log.info("[1/6] Initializing storage client")
        storage_manager = StorageManager(api_key, self.__storage_label)

        if self.__source_prefix:
            storage_handler = SingleStorageHandler(
                storage_manager, self.__source_prefix
            )
        else:
            source_prefixes = self.__get_source_prefixes(storage_manager, context)
            storage_handler = MultiStorageHandler(  # type: ignore
                storage_manager, source_prefixes
            )

        log.info("Verifying access to all prefixes...")
        storage_handler.verify_access()
        log.info("Access verified successfully")

        run(
            context=context,
            dbt_project_zip=self.__dbt_project_zip,
            storage_handler=storage_handler,
            output_prefix=self.__output_prefix,
        )

        log.info("\n" + "=" * 80)
        log.info("dbt Runner Gear - Completed successfully")
        log.info("=" * 80)


def main():
    """Main method for DBT Runner."""

    GearEngine.create_with_parameter_store().run(gear_type=DBTRunnerVisitor)


if __name__ == "__main__":
    main()
