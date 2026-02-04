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
        log.warning(f"Missing required headers, skipping: {missing}")
        return None

    key_pairs = pc.make_struct(table[FieldNames.ADCID], table[FieldNames.NACCID])
    pair_counts = pc.value_counts(key_pairs)

    pair_table = pa.Table.from_struct_array(pair_counts["values"])
    by_naccid = pair_table.group_by(FieldNames.NACCID).aggregate(
        [(FieldNames.ADCID, "count_distinct")]
    )

    results = by_naccid.filter(pc.field(f"{FieldNames.ADCID}_count_distinct") > 1)[
        FieldNames.NACCID
    ]

    return results if results else None


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

    correct_adcid_key = f"{FieldNames.ADCID}_correct"
    correction_table = pa.Table.from_pydict(
        {
            FieldNames.NACCID: list(correct_mapping.keys()),
            correct_adcid_key: list(correct_mapping.values()),
        }
    )

    # join the corrections in and filter out bad rows
    annotated = table.join(
        correction_table, keys=FieldNames.NACCID, join_type="left_outer"
    )
    keep_mask = pc.or_(
        pc.is_null(annotated[correct_adcid_key]),
        pc.equal(annotated[FieldNames.ADCID], annotated[correct_adcid_key]),
    )

    cleaned_table = annotated.filter(keep_mask).remove_column(correct_adcid_key)
    pq.write_table(cleaned_table, output_file)


def check_for_transfers(aggregate_dir: Path, identifiers_mode: IdentifiersMode) -> None:
    """Handle transfer duplicates, e.g. where a NACCID is associated with
    multiple ADCIDs. Need to detect and filter out the rows from the old
    center.

    Args:
        aggregate_dir: Directory containing aggregate parquets to clean
        identifiers_mode: Mode for identifiers repository
    """
    # only instantiate identifiers repo when absolutely needed
    identifiers_repo: Optional[IdentifiersLambdaRepository] = None

    for file in aggregate_dir.rglob("*.parquet"):
        log.info(f"Checking {file} for transfer duplicates...")
        table = pq.read_table(file)

        duplicate_naccids = find_duplicated_naccids(table)
        if not duplicate_naccids:
            continue

        log.info(
            f"{len(duplicate_naccids)} duplicates found for {file}, " + "cleaning up"
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
