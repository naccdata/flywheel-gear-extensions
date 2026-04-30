"""Handles cleaning up transfer duplicates."""

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
from gear_execution.gear_execution import (
    InputFileWrapper,
)

log = logging.getLogger(__name__)


class DuplicatesHandler:
    def __init__(
        self,
        output_dir: Path,
        duplicates_criteria_json: Optional[InputFileWrapper] = None,
        batch_size: int = 100_000,
    ):
        self.__output_dir = output_dir
        self.__batch_size = batch_size

        self.__duplicates_criteria = {}
        if duplicates_criteria_json:
            with open(duplicates_criteria_json.filepath, mode="r") as fh:
                self.__duplicates_criteria = json.load(fh)

    def __find_duplicate_keys(
        self, table_name: str, aggregate_file: Path
    ) -> Optional[Set[Tuple[Any]]]:
        """Find duplicate tuple keys based on the duplicate_mapping criteria.

        Args:
            table_name: name of the table being evaluated
            aggregate_file: The parquet file to check for duplicates
        """
        criteria = self.__duplicates_criteria.get(table_name)

        # if no duplicate criteria, skip
        if not criteria:
            log.warning(
                f"No duplicate criteria provided for table {table_name}, skipping"
                + "duplicates check"
            )
            return None

        parquet_file = pq.ParquetFile(aggregate_file)
        missing = set(criteria) - set(parquet_file.schema.names)
        if missing:
            raise ValueError(
                f"Missing required headers for duplicates check: {missing}"
            )

        # identify duplicates based on all criteria fields
        value_counts: Dict[Tuple, int] = defaultdict(int)

        for batch in parquet_file.iter_batches(batch_size=self.__batch_size):
            table = pa.Table.from_batches([batch])
            fields = [table[x].to_pylist() for x in criteria]

            for key in zip(*fields, strict=True):
                value_counts[key] += 1

        # the zip creates a tuple "key" using all the fields in the criteria
        # duplicates occur where a tuple key appears more than once
        duplicates = {k for k, v in value_counts.items() if v > 1}

        return duplicates

    def __filter_duplicates(
        self, table_name: str, aggregate_file: Path, duplicate_keys: Set[Tuple[Any]]
    ) -> None:
        """Finds rows associated with the duplicate keys from the aggregate
        file and filters them out.

        Args:
            table_name: name of the table being evaluated
            aggregate_file: The parquet file to check for duplicates
            duplicate_keys: Duplicate keys to map to rows to drop
        """
        criteria = self.__duplicates_criteria.get(table_name)

        # if nothing to correct, do nothing
        if not duplicate_keys or not criteria:
            return

        # write results to a tmp file while we're streaming
        # from the original aggregate file
        parquet_file = pq.ParquetFile(aggregate_file)
        tmp_file = aggregate_file.with_suffix(".tmp.parquet")
        schema = parquet_file.schema.to_arrow_schema()
        writer = pq.ParquetWriter(tmp_file, schema)
        duplicates_writer = None

        try:
            for batch in parquet_file.iter_batches(batch_size=self.__batch_size):
                table = pa.Table.from_batches([batch])
                fields = [table[x].to_pylist() for x in criteria]

                # again, the zip creates a tuple "key" using all the fields
                # make a mask of rows to keep
                keep_mask = []
                for key in zip(*fields, strict=True):
                    keep_mask.append(key not in duplicate_keys)

                mask = pa.array(keep_mask)

                # filter table
                filtered_table = table.filter(mask)
                if filtered_table.num_rows > 0:
                    writer.write_table(filtered_table)

                # get duplicates, if any
                duplicates_table = table.filter(pc.invert(mask))  # type: ignore
                if duplicates_table.num_rows > 0:
                    if not duplicates_writer:
                        outfile = (
                            Path(self.__output_dir) / f"{table_name}_duplicates.csv"
                        )
                        duplicates_writer = pcsv.CSVWriter(
                            outfile, duplicates_table.schema
                        )

                    duplicates_writer.write_table(duplicates_table)

        finally:
            writer.close()
            if duplicates_writer:
                duplicates_writer.close()

        # update original file
        os.replace(tmp_file, aggregate_file)

    def handle(self, table: str, aggregate_file: Path) -> None:
        """Handle duplicates based on duplicate criteria.

        Args:
            table: name of the table being evaluated
            aggregate_file: Aggregate parquet file to clean
        """
        duplicate_keys = self.__find_duplicate_keys(table, aggregate_file)
        if not duplicate_keys:
            log.info(f"No duplicates detected in {table}")
            return

        log.info(
            f"{(len(duplicate_keys))} duplicate keys found for {table}, "
            + "dropping associated rows"
        )

        self.__filter_duplicates(table, aggregate_file, duplicate_keys)
