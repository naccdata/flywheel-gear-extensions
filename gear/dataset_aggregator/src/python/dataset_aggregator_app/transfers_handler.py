"""Functions to handle transfer duplicates."""

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Set

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
)
from identifiers.identifiers_repository import IdentifierRepositoryError
from identifiers.model import IdentifiersMode
from lambdas.lambda_function import LambdaClient, create_lambda_client
from nacc_common.field_names import FieldNames

log = logging.getLogger(__name__)


class TransferDuplicateHandler:
    def __init__(self, identifiers_mode: IdentifiersMode, batch_size: int = 100_000):
        self.__identifiers_repo = IdentifiersLambdaRepository(
            client=LambdaClient(client=create_lambda_client()),
            mode=identifiers_mode,
        )
        self.__batch_size = batch_size
        self.__required_headers = {FieldNames.ADCID, FieldNames.NACCID}

    def __find_duplicated_naccids(self, aggregate_file: Path) -> Optional[Set[str]]:
        """Find NACCIDs that are duplicated across multiple ADCIDs. If so,
        likely a transfer.

        Args:
            aggregate_file: The parquet file to check for duplicates
        """
        parquet_file = pq.ParquetFile(aggregate_file)
        missing = self.__required_headers - set(parquet_file.schema.names)
        if missing:
            log.warning(
                f"Missing required headers, skipping duplicate check: {missing}"
            )
            return None

        # keep track of all the NACCID/ADCID pairings; NACCIDs
        # with more than one ADCID will be flagged as a duplicate
        found_pairings = defaultdict(set)
        duplicates = set()

        for batch in parquet_file.iter_batches(batch_size=self.__batch_size):
            table = pa.Table.from_batches([batch])
            naccids = table[FieldNames.NACCID].to_pylist()
            adcids = table[FieldNames.ADCID].to_pylist()

            for naccid, adcid in zip(naccids, adcids, strict=True):
                found_pairings[naccid].add(adcid)
                if len(found_pairings[naccid]) > 1:
                    duplicates.add(naccid)

        return duplicates

    def __clean_transfer_duplicates(
        self, aggregate_file: Path, correct_mapping: Dict[str, int]
    ) -> None:
        """Cleans table by removing rows that do not match the current
        mappings.

        Args:
            aggregate_file: Parquet file to clean
            correct_mapping: Mapping of {naccid: current_adcid}; any other
                ADCIDs attached to this NACCID will have the
                row dropped
        """
        # if nothing to correct, do nothing
        if not correct_mapping:
            return

        # write results to a tmp file while we're streaming
        # from the original aggregate file
        parquet_file = pq.ParquetFile(aggregate_file)
        tmp_file = aggregate_file.with_suffix(".tmp.parquet")
        schema = parquet_file.schema.to_arrow_schema()
        writer = pq.ParquetWriter(tmp_file, schema)

        keys = pa.array(
            correct_mapping.keys(),
            type=schema.field(FieldNames.NACCID).type,
        )
        values = pa.array(
            correct_mapping.values(),
            type=schema.field(FieldNames.ADCID).type,
        )

        try:
            for batch in parquet_file.iter_batches(batch_size=self.__batch_size):
                table = pa.Table.from_batches([batch])

                # get adcid/naccid columns
                adcid_col = table[FieldNames.ADCID]
                naccid_col = table[FieldNames.NACCID]

                # apply corrected values over relevant indexes
                in_mapping = pc.is_in(naccid_col, keys)
                idx = pc.index_in(naccid_col, keys)
                correct_adcid = pc.take(values, idx)

                # build the mask to only keep corrected ADCID/NACCID
                # pairings and those that didn't need fixing
                keep_mask = pc.or_(
                    pc.invert(in_mapping), pc.is_in(adcid_col, correct_adcid)
                )

                # apply filter
                cleaned_table = table.filter(keep_mask)
                writer.write_table(cleaned_table)

        finally:
            writer.close()

        # update original file
        os.replace(tmp_file, aggregate_file)

    def handle(self, aggregate_file: Path) -> None:
        """Handle transfer duplicates, e.g. where a NACCID is associated with
        multiple ADCIDs. Need to detect and filter out the rows from the old
        center.

        Args:
            aggregate_file: Aggregate parquet file to clean
        """
        duplicate_naccids = self.__find_duplicated_naccids(aggregate_file)
        if not duplicate_naccids:
            return

        log.info(
            f"{len(duplicate_naccids)} duplicates found in {aggregate_file}, resolving"
        )

        # query NACCIDs and get the current ADCID
        correct_mapping: Dict[str, int] = {}
        for naccid in duplicate_naccids:
            # for other uses we batch/sleep the lookup, but probably
            # won't have too many in this case
            identifier = self.__identifiers_repo.get(naccid=naccid)
            if not identifier or not identifier.naccid or not identifier.adcid:
                raise IdentifierRepositoryError(
                    f"Failed to find identifiers info for {naccid}"
                )

            correct_mapping[identifier.naccid] = identifier.adcid

        self.__clean_transfer_duplicates(aggregate_file, correct_mapping)
