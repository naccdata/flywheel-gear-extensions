"""Storage Configs; keeps track of and validates prefixes."""

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict

import pyarrow.parquet as pq
from gear_execution.gear_execution import (
    GearExecutionError,
)
from storage.storage import StorageManager


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
    def download(self, target_dir: Path) -> None:
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

    def download(self, target_dir: Path) -> None:
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

    def download(self, target_dir: Path) -> None:
        self.__download_and_aggregate_sources(target_dir)

    def __download_and_aggregate_sources(self, target_dir: Path) -> None:
        """Aggregate data sources into a single parquet.

        Args:
            target_dir: Location to write final aggregation
        """
        # need to open writers for each unique table, and append as we find them
        table_writers = {}

        try:
            for center, source_prefix in self.__source_prefixes.items():
                center_dir = target_dir / center
                self.storage_manager.download_dataset(source_prefix, center_dir)

                # we only really care about the files under tables/
                tables_dir = center_dir / "tables"
                for table in tables_dir.iterdir():
                    if not table.is_dir():
                        continue

                    # assuming there is exactly one parquet for the table
                    parquet_files = list(table.glob("*.parquet"))
                    if len(parquet_files) != 1:
                        raise GearExecutionError(
                            "Did not find exactly one parquet "
                            + f"file for table {table.name} under {source_prefix}"
                        )

                    data = pq.read_table(parquet_files[0])

                    # TODO: this may be a good spot to inject center info,
                    # something like
                    # data.append_column("center", pa.array([center] * data.num_rows)

                    if table.name not in table_writers:
                        table_writers[table.name] = pq.ParquetWriter(
                            target_dir
                            / "tables"
                            / table.name
                            / f"aggregate_{table.name}.parquet",
                            data.schema,
                        )

                    table_writers[table.name].write_table(data)

                    # clean up as we go
                    shutil.rmtree(center_dir)
        except Exception as e:
            raise GearExecutionError(
                f"Failed to download from {source_prefix}: {e}"
            ) from e

        # make sure we close writers
        finally:
            for writer in table_writers.values():
                writer.close()
