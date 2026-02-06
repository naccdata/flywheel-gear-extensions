"""Functions to handle transfer duplicates."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

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


def find_duplicated_naccids(table: pa.Table) -> Optional[List[str]]:
    """Find NACCIDs that are duplicated across multiple ADCIDs. If so, likely a
    transfer.

    Args:
        table: The table to check
    """
    required_headers = {FieldNames.ADCID, FieldNames.NACCID}
    missing = required_headers - set(table.schema.names)
    if missing:
        log.warning(f"Missing required headers, skipping duplicate check: {missing}")
        return None

    # group by distinct adcid/naccid pairs
    by_naccid = table.group_by(FieldNames.NACCID).aggregate(
        [(FieldNames.ADCID, "count_distinct")]
    )

    # get NACCIDs that have more than one ADCID
    duplicated = by_naccid.filter(
        pc.field(f"{FieldNames.ADCID}_count_distinct") > 1
    )[FieldNames.NACCID]

    return duplicated.to_pylist() if len(duplicated) > 0 else None


def clean_table(
    output_file: Path, table: pa.Table, correct_mapping: Dict[str, int]
) -> None:
    """Cleans table by removing rows that do not match the current mappings.

    Args:
        file: file to write results to
        table: the pyarrow table to clean
        correct_mapping: Mapping of {naccid: current_adcid}; any other
            ADCIDs attached to this NACCID will have the
            row dropped
    """
    # get adcid/naccid columns
    adcid_col = table[FieldNames.ADCID]
    naccid_col = table[FieldNames.NACCID]

    keys = pa.array(
        correct_mapping.keys(),
        type=table.schema.field(FieldNames.NACCID).type
    )
    values = pa.array(
        correct_mapping.values(),
        type=table.schema.field(FieldNames.ADCID).type
    )

    # apply corrected values over relevant indexes
    in_mapping = pc.is_in(naccid_col, keys)
    idx = pc.index_in(naccid_col, keys)
    correct_adcid = pc.take(values, idx)

    # build the mask to only keep corrected ADCID/NACCID
    # pairings and those that didn't need fixing
    keep_mask = pc.or_(
        pc.invert(in_mapping),
        pc.is_in(adcid_col, correct_adcid)
    )
    cleaned_table = table.filter(keep_mask)

    pq.write_table(cleaned_table, output_file)


def check_for_transfers(aggregate_dir: Path, identifiers_mode: IdentifiersMode) -> None:
    """Handle transfer duplicates, e.g. where a NACCID is associated with
    multiple ADCIDs. Need to detect and filter out the rows from the old
    center.

    Args:
        aggregate_dir: Directory containing aggregate parquets to clean
        identifiers_mode: Mode for identifiers repository
    """
    log.info(f"Checking for transfer duplicates...")

    # only instantiate identifiers repo when absolutely needed
    identifiers_repo: Optional[IdentifiersLambdaRepository] = None

    for file in aggregate_dir.rglob("*.parquet"):
        table = pq.read_table(file)

        duplicate_naccids = find_duplicated_naccids(table)
        if not duplicate_naccids:
            continue

        log.info(
            f"{len(duplicate_naccids)} duplicates found for {file}, resolving"
        )

        if not identifiers_repo:
            identifiers_repo = IdentifiersLambdaRepository(
                client=LambdaClient(client=create_lambda_client()),
                mode=identifiers_mode,
            )

        # query NACCIDs and get the current ADCID
        correct_mapping: Dict[str, int] = {}
        for naccid in duplicate_naccids:
            # for other uses we batch/sleep the lookup, but probably
            # won't have too many in this case
            identifier = identifiers_repo.get(naccid=naccid)
            if not identifier or not identifier.naccid or not identifier.adcid:
                raise IdentifierRepositoryError(
                    f"Failed to find identifiers info for {naccid}"
                )

            correct_mapping[identifier.naccid] = identifier.adcid

        # clean the table and write back to same file
        clean_table(file, table, correct_mapping)
