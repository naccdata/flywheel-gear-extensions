"""Entry script for Dataset Aggregator."""

import logging

from pydantic import ValidationError
from typing import Any, Dict, List, Optional

from dataset_aggregator_app.main import FWDataset, run
from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore
from s3.s3_bucket import S3BucketInterface

log = logging.getLogger(__name__)


class DatasetAggregatorVisitor(GearExecutionEnvironment):
    """Visitor for the Dataset Aggregator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        target_project: str,
        output_uri: str,
        file_type: str,
    ):
        super().__init__(client=client)
        self.__target_project = target_project
        self.__output_uri = output_uri
        self.__file_type = file_type

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'DatasetAggregatorVisitor':
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

        return DatasetAggregatorVisitor(
            client=client,
            target_project=context.config.get("target_project", None),
            output_uri=context.config.get("output_uri", None),
            file_type=context.config.get("file_type", None),
        )

    def __get_source_prefixes(self, center_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Create source prefixes from center map by looking up which centers
        have the specified target project.

        Args:
            center_ids: List of center IDs to aggregate
        Returns:
            Mapping of bucket to center to latest prefix, along with the s3 interface, e.g.
            {
                "my-bucket-1": {
                    "interface": S3BucketInterface instance,
                    "centers": {
                        "center-1": "most-recent-prefix-for-center-1",
                        "center-2": "most/recent/prefix/for/center-2"
                    }
                },
                ...
            }
        """
        source_prefixes: Dict[str, Dict[str, Any]] = {}

        # keep track of interfaces so we don't instantiate more than necessary
        # since they're all likely to belong to the same bucket anyways
        interfaces: Dict[str, S3BucketInterface] = {}

        log.info(f"Looking up latest datasets for {self.__target_project} projects")

        for center in center_ids:
            try:
                project = self.proxy.lookup(f"{center}/{self.__target_project}")
            except ApiException:
                log.warning(
                    f"No {self.__target_project} project found for "
                    + f"center {center}, skipping"
                )
                continue

            try:
                project = project.reload()
                dataset = FWDataset(project.info.get("dataset", {}))
            except (ApiException, ValidationError) as e:
                log.error(
                    f"dataset metadata not defined for {center}/{self.__target_project}"
                )
                continue

            # if first time encountering this particular bucket
            if dataset.bucket not in source_prefixes:
                source_prefixes[dataset.bucket] = {
                    "interface": S3BucketInterface.create_from_environment(dataset.bucket),
                    "centers": {}

                }

            latest_dataset = dataset.get_latest_version(interfaces[dataset.bucket])
            if not latest_dataset:
                log.warning(
                    f"No latest dataset found for {center}/{self.__target_project}"
                )
                continue

            source_prefixes[dataset.bucket]['centers'][center] = latest_dataset

        # remove buckets that have no centers with latest datasets
        source_prefixes = {k: v if v.get("centers")
                           for k, v in source_prefixes.items()}

        if not source_prefixes:
            raise GearExecutionError(
                f"No datasets found for project {self.__target_project}"
            )

        return source_prefixes

    def run(self, context: GearToolkitContext) -> None:

        source_prefixes = self.__get_source_prefixes(self.get_center_ids(context))

        run(
            proxy=self.proxy,
            source_prefixes=source_prefixes,
            output_uri=self.__output_uri,
            file_type=self.__file_type,
            dry_run=self.client.dry_run,
        )


def main():
    """Main method for Dataset Aggregator."""

    GearEngine.create_with_parameter_store().run(gear_type=DatasetAggregatorVisitor)


if __name__ == "__main__":
    main()
