"""Storage handler; handles verifying and downloading dataset(s) from
storage."""

import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict

import pyarrow.parquet as pq
from gear_execution.gear_execution import (
    GearExecutionError,
)
from storage.storage import StorageManager

log = logging.getLogger(__name__)


class StorageHandler(ABC):
    def __init__(self, storage_manager: StorageManager) -> None:
        self.__storage_manager = storage_manager

    @property
    def storage_manager(self) -> StorageManager:
        return self.__storage_manager

    @classmethod
    def validate_prefix(cls, prefix: str) -> str:
        """Ensure prefixes have no trailing backslash."""
        stripped_prefix = prefix.rstrip("/")
        if not stripped_prefix:
            raise GearExecutionError(f"Prefix cannot be empty: {prefix}")

        return stripped_prefix

    def verify_access(self) -> None:
        self.storage_manager.verify_access(None)

    @abstractmethod
    def download(self, target_dir: Path, tables_only: bool = True) -> None:
        """Download data."""
        pass


class SingleStorageHandler(StorageHandler):
    """For when the source data comes from a singular source."""

    def __init__(self, storage_manager: StorageManager, source_prefix: str) -> None:
        super().__init__(storage_manager)

        self.__source_prefix = self.validate_prefix(source_prefix)

    def verify_access(self) -> None:
        """Verify the prefix is accessible."""
        self.storage_manager.verify_access(self.__source_prefix)

    def download(self, target_dir: Path, tables_only: bool = True) -> None:
        """Download the dataset."""
        if tables_only:
            self.storage_manager.download_dataset(
                f"{self.__source_prefix}/tables", target_dir / "tables")
        else:
            self.storage_manager.download_dataset(self.__source_prefix, target_dir)


class MultiStorageHandler(StorageHandler):
    """For when the source data comes from an aggregation of sources."""

    def __init__(
        self, storage_manager: StorageManager, source_prefixes: Dict[str, str]
    ) -> None:
        super().__init__(storage_manager)

        self.__source_prefixes = {
            k: self.validate_prefix(v) for k, v in source_prefixes.items()
        }

    def verify_access(self) -> None:
        """Verify the prefix is accessible."""
        for prefix in self.__source_prefixes.values():
            self.storage_manager.verify_access(prefix)

    def download(self, target_dir: Path, tables_only: bool = True) -> None:
        """Download the dataset."""
        self.__download_and_aggregate_sources(target_dir, tables_only)

    def __download_and_aggregate_sources(self, target_dir: Path, tables_only: bool = True) -> None:
        """Aggregate data sources into a single parquet.

        Args:
            target_dir: Location to write final aggregation
            tables_only: Whether or not to only download tables, which is
                typically all we care about (otherwise we also download things
                like the snapshot provenance which can take up a lot of space)
        """
        # need to open writers for each unique table, and append as we find them
        table_writers = {}

        try:
            for center, source_prefix in self.__source_prefixes.items():
                center_dir = target_dir / center
                tables_dir = center_dir / "tables"
                download_dir = tables_dir if tables_only else center_dir

                if tables_only:
                    self.storage_manager.download_dataset(
                        f"{source_prefix}/tables", tables_dir)
                else:
                    self.storage_manager.download_dataset(source_prefix, center_dir)

                for table in tables_dir.iterdir():
                    if not table.is_dir():
                        continue

                    # assuming there is exactly one parquet for the table
                    parquet_files = list(table.glob("*.parquet"))
                    if len(parquet_files) != 1:
                        raise GearExecutionError(
                            f"Did not find exactly one parquet file for table {table.name}"
                        )

                    data = pq.read_table(parquet_files[0])

                    if table.name not in table_writers:
                        target_table_dir = target_dir / "tables" / table.name
                        target_table_dir.mkdir(parents=True, exist_ok=True)

                        table_writers[table.name] = pq.ParquetWriter(
                            target_table_dir / f"aggregate_{table.name}.parquet",
                            data.schema,
                        )

                    table_writers[table.name].write_table(data)

                # clean up each center once done with it
                shutil.rmtree(center_dir)
        except Exception as e:
            raise GearExecutionError(
                f"Failed to download from {source_prefix}: {e}"
            ) from e

        # make sure we close writers
        finally:
            for writer in table_writers.values():
                writer.close()
