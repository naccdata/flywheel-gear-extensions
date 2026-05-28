"""Handles cleaning up transfer duplicates."""

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
from gear_execution.gear_execution import (
    InputFileWrapper,
)
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
)
from identifiers.identifiers_repository import (
    IdentifierObject,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifiersMode
from lambdas.lambda_function import LambdaClient, create_lambda_client
from pydantic import BaseModel

log = logging.getLogger(__name__)


class DuplicatesCriteria(BaseModel):
    criteria: List[str]
    on_duplicate: Literal["active_only", "keep_all", "drop_all"] = "drop_all"


class DuplicatesHandler:
    def __init__(
        self,
        identifiers_mode: IdentifiersMode,
        output_dir: Path,
        duplicates_criteria_json: Optional[InputFileWrapper] = None,
        batch_size: int = 100_000,
    ):
        self.__output_dir = output_dir
        self.__batch_size = batch_size

        self.__duplicates_criteria: Dict[str, DuplicatesCriteria] = {}
        if duplicates_criteria_json:
            with open(duplicates_criteria_json.filepath, mode="r") as fh:
                for table, data in json.load(fh).items():
                    self.__duplicates_criteria[table] = DuplicatesCriteria(**data)

        self.__identifiers_repo = IdentifiersLambdaRepository(
            client=LambdaClient(client=create_lambda_client()),
            mode=identifiers_mode,
        )

        # cache to avoid requerying the identifiers repo over and over
        # since it's done for each batch of a parquet file
        self.__identifiers_cache: Dict[str, List[IdentifierObject]] = {}

    def __find_duplicate_keys(
        self, table_name: str, aggregate_file: Path
    ) -> Optional[Set[Tuple[Any]]]:
        """Find duplicate tuple keys based on the duplicate_mapping criteria.
        Since we are doing this in batches, we need to count unique key tuples
        across each batch to detect duplicates.

        Args:
            table_name: name of the table being evaluated
            aggregate_file: The parquet file to check for duplicates
        """
        criteria_block = self.__duplicates_criteria.get(table_name)

        # if no duplicate criteria, skip
        if not criteria_block or not criteria_block.criteria:
            log.warning(
                f"No duplicate criteria provided for table {table_name}, skipping"
                + "duplicates check"
            )
            return None

        criteria = criteria_block.criteria
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

    def __apply_duplicate_rules(  # noqa: C901
        self, rule: str, keep_mask: pa.array, table: pa.Table
    ) -> Tuple[pa.Table, pa.Table | None]:
        """Check if duplicates were caused by a transfer and apply one of the
        following rules if so:

        active_only: Keep only the active center, drop the inactive center(s)
        keep_all: Keep all rows
        drop_all: Drop all rows

        Args:
            rule: rule to apply (active, keep_all, drop_all)
            keep_mask: The mask indicating values to keep just solely
                based on duplicates
            table: The (batch) table to filter
        Returns:
            The filtered table and the dropped table (if any)
        """
        log.info(f"Applying rule {rule}")

        # if keeping all, do nothing
        if rule == "keep_all":
            return table, None

        # get duplicates, if any
        duplicates_table = table.filter(pc.invert(keep_mask))  # type: ignore

        # if no duplicates in this batch, nothing to do
        if duplicates_table.num_rows == 0:
            return table, None

        # if rule is drop-all, just drop all
        if rule == "drop_all":
            return table.filter(keep_mask), duplicates_table

        # Next is basically the logic for active_only, which is a fair bit more
        # complicated.
        # We first have to query the identifiers API to know if an ADCID is the
        # current center for that NACCID.
        # We then create a filter using all the NACCID/ADCID pairs where the ADCID is
        # not the current center to create a new mask on which rows to drop.

        # Group to get a mapping of NACCID -> List[ADCIDs]
        grouped = duplicates_table.group_by("naccid").aggregate([("adcid", "list")])
        grouped_identifiers = {
            row["naccid"]: set(row["adcid_list"]) for row in grouped.to_pylist()
        }

        # query the identifiers repo to get the active ADCID, and keep track of
        # NACCID/ADCID pairs to drop
        # if the NACCID has no current ADCID, drop all rows, as may be a data issue
        pairs_to_drop: Set[Tuple[str, int]] = set([])

        for naccid, adcids in grouped_identifiers.items():
            current_adcid = None

            if naccid not in self.__identifiers_cache:
                result = self.__identifiers_repo.list(naccid=naccid)
                if not result:
                    raise IdentifierRepositoryError(
                        f"Failed to find identifiers info for {naccid}"
                    )

                self.__identifiers_cache[naccid] = result

            for identifier in self.__identifiers_cache[naccid]:
                if identifier.active:
                    current_adcid = identifier.adcid

            if not current_adcid:
                log.warning(
                    f"No current ADCID found for {naccid}, dropping all "
                    + f"rows for {naccid}"
                )
                pairs_to_drop.update((naccid, adcid) for adcid in adcids)
                continue

            # determine which to drop
            for adcid in adcids:
                if adcid != current_adcid:
                    pairs_to_drop.add((naccid, adcid))

        # if no pairs to drop in this batch, just return as-is
        if not pairs_to_drop:
            return table, None

        log.info(f"Dropping the following inactive pairs: {pairs_to_drop}")

        # Drop any rows that have the NACCID/ADCID pairings
        # Convert pairs to a table that can be used to filter the table
        drop_column = "__to_drop__"
        drop_table = pa.table(
            {
                "naccid": pa.array(
                    [n for n, _ in pairs_to_drop],
                    type=table.schema.field("naccid").type,
                ),
                "adcid": pa.array(
                    [a for _, a in pairs_to_drop],
                    type=table.schema.field("adcid").type,
                ),
                drop_column: pa.array([True] * len(pairs_to_drop)),
            }
        )

        # join the tables, and find rows marked as dropped to build the mask
        joined = table.join(
            drop_table, keys=["naccid", "adcid"], join_type="left outer"
        )

        drop_mask = pc.fill_null(joined[drop_column], False)  # type: ignore[attr-defined]

        # apply new filter
        filtered_table = joined.filter(
            pc.invert(drop_mask)  # type: ignore[attr-defined]
        ).drop_columns([drop_column])
        dropped_table = joined.filter(drop_mask).drop_columns([drop_column])

        log.info(f"Dropped {dropped_table.num_rows} duplicate/invalid rows")
        return filtered_table, dropped_table

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
        criteria_block = self.__duplicates_criteria.get(table_name)

        # if nothing to correct, do nothing
        if not duplicate_keys or not criteria_block or not criteria_block.criteria:
            return

        criteria = criteria_block.criteria

        # write results to a tmp file while we're streaming
        # from the original aggregate file
        parquet_file = pq.ParquetFile(aggregate_file)
        tmp_file = aggregate_file.with_suffix(".tmp.parquet")
        schema = parquet_file.schema.to_arrow_schema()
        writer = pq.ParquetWriter(tmp_file, schema)
        dropped_writer = None

        try:
            for batch in parquet_file.iter_batches(batch_size=self.__batch_size):
                table = pa.Table.from_batches([batch])
                fields = [table[x].to_pylist() for x in criteria]

                # again, the zip creates a tuple "key" using all the fields
                # make a mask of rows to keep
                keep_mask = []
                for key in zip(*fields, strict=True):
                    keep_mask.append(key not in duplicate_keys)

                filtered_table, dropped_table = self.__apply_duplicate_rules(
                    rule=criteria_block.on_duplicate,
                    keep_mask=pa.array(keep_mask),
                    table=table,
                )

                if filtered_table.num_rows > 0:
                    writer.write_table(filtered_table)

                if dropped_table is not None and dropped_table.num_rows > 0:
                    if not dropped_writer:
                        outfile = Path(self.__output_dir) / f"{table_name}_dropped.csv"
                        dropped_writer = pcsv.CSVWriter(outfile, dropped_table.schema)

                    dropped_writer.write_table(dropped_table)

        finally:
            writer.close()
            if dropped_writer:
                dropped_writer.close()

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
            + "handling duplicate logic"
        )

        self.__filter_duplicates(table, aggregate_file, duplicate_keys)
