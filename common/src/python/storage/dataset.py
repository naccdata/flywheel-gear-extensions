"""Models to handle FW's datasets.

FW has its own fw-dataset library; however this library causes a lot of
package versioning conflicts and is also a bit overkill for what we
generally need, so using our own version here.
"""

import json
import logging
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import pyarrow.parquet as pq
from pydantic import BaseModel, root_validator
from s3.s3_bucket import S3BucketInterface

log = logging.getLogger(__name__)

DATASET_DATE_FMT = "%Y-%m-%dT%H:%M:%S.%f%z"


class FWDatasetError(Exception):
    pass


class FWDataset(BaseModel):
    """Models the FW Dataset metadata."""

    bucket: str
    prefix: str
    storage_id: str
    storage_label: Optional[str]
    type: Literal["s3"]  # other types allowed but we only work with S3

    @property
    def full_uri(self) -> str:
        """Return the full S3 URI."""
        return f"{self.bucket}/{self.prefix}"

    @root_validator(pre=True)
    def storage_label_alias(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """storage_label can also be storage, seems to depend on when the
        dataset was made."""
        if 'storage_label' not in values and 'label' in values:
            values['storage_label'] = values.pop('label')
        return values


class AggregateDataset(ABC):
    """Class to handle aggregating datasets from the same bucket."""

    def __init__(
        self, bucket: str, project: str, datasets: Dict[str, FWDataset]
    ) -> None:
        """Initializer.

        Args:
            bucket: Common bucket; assumes all datasets live in this bucket
            project: Project the datasets are coming from
            datasets: Mapping of keys (center name) to FW Datasets
        """
        # make sure all datasets live in the specified bucket
        for dataset in datasets.values():
            if dataset.bucket != bucket:
                raise FWDatasetError(
                    "Mismatched dataset and bucket; cannot instantiate AggregateDataset"
                )

        self.__bucket = bucket
        self.__project = project
        self.__datasets = datasets

        # make interface for the bucket
        self.__s3_interface = S3BucketInterface.create_from_environment(bucket)

    @property
    def bucket(self) -> str:
        return self.__bucket

    @property
    def s3_interface(self) -> S3BucketInterface:
        return self.__s3_interface

    def get_latest_version(self, dataset: FWDataset) -> Optional[str]:
        """Get latest dataset version under the specified dataset.

        Args:
            dataset: FWDataset to find latest version for
        Returns:
            Prefix of the latest dataset version, if found
        """
        if dataset.bucket != self.bucket:
            raise FWDatasetError(
                "Mismatched dataset and bucket; unable to find latest version"
            )

        target_path = "/provenance/dataset_description.json"
        latest_creation = None
        latest_dataset = None

        try:
            # iterate over the description JSONs to get the creation dates
            found_descriptions = self.__s3_interface.list_directory(
                dataset.prefix, glob=f"*{target_path}"
            )

            for filepath in found_descriptions:
                with self.__s3_interface.read_data(filepath) as fh:
                    description = json.load(fh)

                    created = datetime.strptime(
                        description["created"], DATASET_DATE_FMT
                    )
                    if not latest_creation or latest_creation < created:
                        latest_creation = created
                        latest_dataset = filepath

        except Exception as e:
            raise FWDatasetError(f"Failed to inspect '{filepath}': {e}") from e

        if latest_dataset:
            # remove target_path suffix to get prefix of version itself
            latest_dataset = latest_dataset.removesuffix(target_path)
            log.info(f"Found latest dataset: {latest_dataset}")

        return latest_dataset

    def get_latest_versions(self) -> Dict[str, str]:
        """Get latest versions for all datasets.

        Returns:
            Mapping of keys to their most recent datasets
        """
        latest_versions: Dict[str, str] = {}

        for center, dataset in self.__datasets.items():
            prefix = self.get_latest_version(dataset)
            if not prefix:
                log.warning(f"No latest dataset found for {center}/{self.__project}")
                continue

            latest_versions[center] = prefix

        return latest_versions

    @abstractmethod
    def download_and_aggregate(
        self,
        aggregate_dir: Path,
        tmp_dir: Path,
        writers: Dict[str, Any],
    ) -> None:
        """Abstract method to handle the download and aggregation step."""
        pass


class ParquetAggregateDataset(AggregateDataset):
    """Class to handle specifically downloading table parquets from
    datasets."""

    def download_and_aggregate(
        self,
        aggregate_dir: Path,
        tmp_dir: Path,
        writers: Dict[str, Any],
    ) -> None:
        """Download and write into the open table writers. Assumes under
        tables/ directory, and contains parquets.

        Args:
            aggregate_dir: Target directory to write aggregate results to
            tmp_dir: Tmp directory to write working results to
            writers: mapping of table to ParquetWriter writer handlers to
                append results into
        """
        log.info(f"Grabbing latest datasets under {self.bucket}...")
        latest_versions = self.get_latest_versions()

        log.info(f"Downloading from {self.bucket} for {len(latest_versions)} centers")

        for center, prefix in latest_versions.items():
            log.info(f"Downloading data for {center}...")

            center_dir = tmp_dir / center
            tables_dir = center_dir / "tables"

            self.s3_interface.download_files(
                f"{prefix}/tables", tables_dir, glob="*.parquet"
            )

            for table in tables_dir.iterdir():
                if not table.is_dir():
                    continue

                # assuming there is exactly one parquet for the table
                parquet_files = list(table.glob("*.parquet"))
                if len(parquet_files) != 1:
                    raise FWDatasetError(
                        "Did not find exactly one parquet file for table "
                        + f"{table.name}"
                    )

                data = pq.read_table(parquet_files[0])

                if table.name not in writers:
                    aggregate_table_dir = aggregate_dir / "tables" / table.name
                    aggregate_table_dir.mkdir(parents=True, exist_ok=True)

                    writers[table.name] = pq.ParquetWriter(
                        aggregate_table_dir / f"aggregate_{table.name}.parquet",
                        data.schema,
                    )

                writers[table.name].write_table(data)

            # clean up each center once done with it
            shutil.rmtree(center_dir)
