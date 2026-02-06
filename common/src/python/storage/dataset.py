"""Models to handle FW's datasets."""

import io
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

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
        if "storage_label" not in values and "label" in values:
            values["storage_label"] = values.pop("label")
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

        # make interface for the bucket
        self.__s3_interface = S3BucketInterface.create_from_environment(bucket)

        # get latest versions and tables
        self.__latest_versions, self.__tables = self.__get_latest_versions(datasets)

    @property
    def bucket(self) -> str:
        return self.__bucket

    @property
    def s3_interface(self) -> S3BucketInterface:
        return self.__s3_interface

    @property
    def latest_versions(self) -> Dict[str, str]:
        return self.__latest_versions

    @property
    def tables(self) -> Set[str]:
        return self.__tables

    def __get_latest_versions(
        self, datasets: Dict[str, FWDataset]
    ) -> Tuple[Dict[str, str], Set[str]]:
        """Get latest versions and all tables for all datasets.

        Returns:
            Mapping of keys to their most recent datasets and a list
                of all possible tables
        """
        log.info(f"Grabbing latest datasets under {self.bucket}...")
        latest_versions: Dict[str, str] = {}
        all_tables = set()

        for center, dataset in datasets.items():
            prefix, tables = self.get_latest_version(dataset)
            if not prefix:
                log.warning(f"No latest dataset found for {center}/{self.__project}")
                continue

            latest_versions[center] = prefix
            if tables:
                all_tables.update(tables)

        return latest_versions, all_tables

    def get_latest_version(
        self, dataset: FWDataset
    ) -> Tuple[Optional[str], Optional[List[str]]]:
        """Get latest dataset version and tables under the specified dataset.

        Args:
            dataset: FWDataset to find latest version for
        Returns:
            Prefix of the latest dataset version and its tables, if found
        """
        if dataset.bucket != self.bucket:
            raise FWDatasetError(
                "Mismatched dataset and bucket; unable to find latest version"
            )

        target_path = "/provenance/dataset_description.json"
        latest_creation = None
        latest_dataset = None
        tables = None

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
                        tables = description["tables"].keys()

        except Exception as e:
            raise FWDatasetError(f"Failed to inspect '{filepath}': {e}") from e

        if latest_dataset:
            # if no tables, not worth keeping track of
            if not tables:
                return None, None

            # remove target_path suffix to get prefix of version itself
            latest_dataset = latest_dataset.removesuffix(target_path)
            log.info(
                f"Found latest dataset: {latest_dataset} with {len(tables)} tables"
            )

        return latest_dataset, tables

    @abstractmethod
    def aggregate_table(
        self,
        table: str,
        aggregate_dir: Path,
        file_prefix: str = "aggregate_",
        batch_size: int = 100_000,
    ) -> Path:
        """Abstract method to handle the download and aggregation step for a
        single table."""
        pass


class ParquetAggregateDataset(AggregateDataset):
    """Class to handle specifically downloading table parquets from
    datasets."""

    def aggregate_table(
        self,
        table: str,
        aggregate_dir: Path,
        file_prefix: str = "aggregate_",
        batch_size: int = 100_000,
    ) -> Path:
        """Download and write the specified table into the open table writer.
        Assumes under tables/ directory, and contains parquets.

        Args:
            table: specific table to aggregate
            aggregate_dir: Target directory to write aggregate results to
            file_prefix: Prefix to give the resulting aggregate file.
                The table name will be appended to it.
            batch_size: batch size for streaming data

        Returns:
            Path to the aggregate file
        """
        if table not in self.tables:
            raise FWDatasetError(f"Table is not defined in datasets {table}")

        log.info(
            f"Aggregating table {table} from {self.bucket} for "
            + f"{len(self.latest_versions)} centers..."
        )

        # create file handler
        aggregate_table_dir = aggregate_dir / "tables" / table
        aggregate_table_dir.mkdir(parents=True, exist_ok=True)
        outfile = aggregate_table_dir / f"{file_prefix}{table}.parquet"
        writer = None

        try:
            for center, prefix in self.latest_versions.items():
                log.debug(f"Downloading data for {center}...")

                # assuming there is at most exactly one parquet for the table
                s3_files = self.s3_interface.list_directory(
                    f"{prefix}/tables/{table}", glob="*.parquet"
                )

                if not s3_files:
                    continue

                if len(s3_files) != 1:
                    raise FWDatasetError(
                        "Did not find exactly one parquet file for table "
                        + f"{table} for center {center}"
                    )

                # tried using pyarrow's s3filesystem at first for streaming
                # but it was incredibly slow; for now the center-specific files
                # are small enough it is probably okay to just load into memory
                body = self.s3_interface.get_file_object(s3_files[0])["Body"]
                data = pq.read_table(io.BytesIO(body.read()))
                if not writer:
                    writer = pq.ParquetWriter(outfile, schema=data.schema)

                writer.write_table(data)
        finally:
            if writer:
                writer.close()

        log.info(f"Successfully aggregated table {table}")
        return outfile
