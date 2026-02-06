"""Entry script for Dataset Aggregator."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from identifiers.model import IdentifiersMode
from inputs.parameter_store import ParameterStore
from pydantic import ValidationError
from storage.dataset import (
    AggregateDataset,
    FWDataset,
    ParquetAggregateDataset,
)

from dataset_aggregator_app.main import run

log = logging.getLogger(__name__)


class DatasetAggregatorVisitor(GearExecutionEnvironment):
    """Visitor for the Dataset Aggregator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        target_project: str,
        output_uri: str,
        identifiers_mode: IdentifiersMode,
    ):
        super().__init__(client=client)
        self.__target_project = target_project
        self.__output_uri = output_uri
        self.__identifiers_mode = identifiers_mode

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "DatasetAggregatorVisitor":
        """Creates a Dataset Aggregator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        target_project = context.config.get("target_project", None)
        if not target_project:
            raise GearExecutionError("target_project required")

        output_uri = context.config.get("output_uri", None)
        if not output_uri:
            raise GearExecutionError("output_uri required")

        identifiers_mode = context.config.get("identifiers_mode", "prod")
        if identifiers_mode not in ["dev", "prod"]:
            raise GearExecutionError(f"invalid identifiers mode: {identifiers_mode}")

        return DatasetAggregatorVisitor(
            client=client,
            target_project=target_project,
            output_uri=output_uri.rstrip("/"),
            identifiers_mode=identifiers_mode,
        )

    def __group_datasets(self, center_ids: List[str]) -> AggregateDataset:
        """Get datasets for each center ID by looking up which centers have the
        specified target project and dataset metadata.

        Args:
            center_ids: List of center IDs to aggregate
        Returns:
            AggregateDataset, which has collected all found datasets
        """
        log.info(f"Looking up dataset metadata for {self.__target_project} projects...")
        datasets: Dict[str, FWDataset] = {}
        bucket = None

        for center in center_ids:
            try:
                project = self.proxy.lookup(f"{center}/{self.__target_project}")
            except ApiException:
                log.warning(
                    f"No {self.__target_project} project found for {center}, "
                    + "skipping"
                )
                continue

            try:
                project = project.reload()
                dataset_metadata = project.info.get("dataset", {})
                if not dataset_metadata:
                    log.warning(
                        "dataset metadata not defined for "
                        + f"{center}/{self.__target_project}"
                    )
                    continue

                dataset = FWDataset(**dataset_metadata)
            except (ApiException, ValidationError) as e:
                raise GearExecutionError(
                    "failed to parse dataset metadata for "
                    + f"{center}/{self.__target_project}: {e}"
                ) from e

            log.info(f"found dataset metadata for {center}/{self.__target_project}")
            if not bucket:
                bucket = dataset.bucket

            if bucket != dataset.bucket:
                raise GearExecutionError(
                    f"Multiple buckets found ({bucket} and {dataset.bucket}); "
                    + "cannot aggregate"
                )

            datasets[center] = dataset

        if not datasets or not bucket:
            raise GearExecutionError(
                f"No datasets found in centers for project {self.__target_project}"
            )

        # TODO: can support other filetypes like csv/json?
        return ParquetAggregateDataset(
            bucket=bucket,
            project=self.__target_project,
            datasets=datasets,
        )

    def run(self, context: GearToolkitContext) -> None:
        aggregate = self.__group_datasets(self.get_center_ids(context))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        run(
            context=context,
            aggregate=aggregate,
            output_uri=f"{self.__output_uri}/{timestamp}",
            identifiers_mode=self.__identifiers_mode,
            dry_run=self.client.dry_run,
        )


def main():
    """Main method for Dataset Aggregator."""
    GearEngine.create_with_parameter_store().run(gear_type=DatasetAggregatorVisitor)


if __name__ == "__main__":
    main()
