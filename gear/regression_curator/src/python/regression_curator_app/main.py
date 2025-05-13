"""Defines Regression Curator."""
import csv
import logging
from typing import List, MutableMapping, Set

from botocore.response import StreamingBody
from curator.regression_curator import RegressionCurator
from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from outputs.errors import ListErrorWriter, unexpected_value_error
from s3.s3_client import S3BucketReader

log = logging.getLogger(__name__)


def localize_s3_file(s3_file: str) -> StreamingBody:
    """Localizess the S3 file and returns the StreamingBody."""
    log.info(f"Localizing file from {s3_qaf_file}")
    s3_qaf_file = s3_qaf_file.strip().replace('s3://', '')
    s3_bucket = '/'.join(s3_qaf_file.split('/')[:-1])
    filename = s3_qaf_file.split('/')[-1]

    s3_client = S3BucketReader.create_from_environment(s3_bucket)
    if not s3_client:
        raise GearExecutionError(f'Unable to access S3 bucket {s3_bucket}')

    # return body
    return s3_client.get_file_object(filename)['Body']


def process_header(header: List[str], keep_fields: List[str]) -> List[str]:
    """Process the header line.

    Args:
        header: Header line to process
        keep_fields: Required fields in the header.
    """
    header = [x.lower() for x in header]
    missing = []
    for required in keep_fields:
        if required not in header:
            missing.append(required)

    if missing:
        raise GearExecutionError(
            f'Required fields not found in QAF header: {missing}')

    # make lowercase
    return header


def localize_qaf(s3_qaf_file: str, keep_fields: List[str],
                 error_writer: ListErrorWriter) -> MutableMapping:
    """Localizes the QAF from S3 and converts to JSON. Only retains NACC* and
    NGDS* derived variables, visitdate, and fields specified by the keep_fields
    parameter. Assumes no case-sensitivity and converts headers to lowercase.

    Args:
        s3_qaf_file: S3 QAF file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
        error_writer: MPListErrorWriter to write errors to
    Returns:
        Baseline mapping from NACCID to list of entries from the QAF
    """
    body = localize_s3_file(s3_qaf_file)
    header = None
    baseline: MutableMapping = {}
    duplicates: Set[str] = set()

    # the QAF is extremely large, so stream and process by line
    # by only retaining a subset of fields, should help reduce size
    for row in body.iter_lines():
        row = row.decode('utf-8')

        if not header:
            row = next(csv.reader([row]))
            header = process_header(row, keep_fields)
            continue

        row = next(csv.DictReader([row], fieldnames=header, strict=True))

        # grab subset of fields and create visitdate
        naccid = row['naccid']
        visitdate = (f"{int(row['visityr']):04d}-" +
                     f"{int(row['visitmo']):02d}-" +
                     f"{int(row['visitday']):02d}")

        row_data = {'visitdate': visitdate}
        row_data.update({
            k: v
            for k, v in row.items()
            if k in keep_fields or k.startswith('nacc') or k.startswith('ngds')
        })

        key = f'{naccid}_{visitdate}'

        # the duplicate situation shouldn't happen but apparently does exist in the QAF
        # for now, drop as we can't accurately map it
        if key in baseline:
            msg = f"Duplicate key derived from QAF, dropping: {key}"
            log.warning(msg)
            error_writer.write(
                unexpected_value_error(field="naccid",
                                       value=key,
                                       expected="unique key",
                                       message=msg))

            baseline.pop(key)
            duplicates.add(key)  # in case there are triplicates or greater

        if key not in duplicates:
            baseline[key] = row_data

    log.info(f"Loaded {num_records} records from QAF baseline")
    return baseline


def localize_mqt(s3_mqt_file: str) -> MutableMapping:
    """Localizes the MQT baseline from S3 and converts to JSON.
    Assumes no case-sensitivity and converts headers to lowercase.

    Args:
        s3_mqt_file: S3 QAF file to pull baseline from
    Returns:
        Baseline mapping from NACCID to list of entries from the MQT project
    """
    body = localize_s3_file(s3_qaf_file)
    header = None
    baseline: MutableMapping = {}

    # the MQT isn't as large but should also be streamed
    # in this case we read in all the columns though
    for row in body.iter_lines():
        row = row.decode('utf-8')

        if not header:
            row = next(csv.reader([row]))
            header = process_header(row, keep_fields)
            continue

        row = next(csv.DictReader([row], fieldnames=header, strict=True))
        naccid = row['naccid']

        # there should only be one record for each naccid in MQT
        if naccid in baseline:
            raise GearExecutionError(f"Duplicate records found for {naccid}")

        baseline[naccid] = row_data

    log.info(f"Loaded {len(baseline)} records from MQT baseline")
    return baseline


def run(context: GearToolkitContext,
        s3_qaf_file: str | None,
        s3_mqt_file: str | None,
        keep_fields: List[str],
        scheduler: ProjectCurationScheduler,
        error_writer: ListErrorWriter) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        s3_qaf_file: S3 QAF file to pull baseline from
        s3_mqt_file: S3 MQT file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
        scheduler: Schedules the files to be curated
        error_writer: Multi-processing error writer
    """
    qaf_baseline = localize_qaf(s3_qaf_file, keep_fields, error_writer) \
        if s3_qaf_file is not None else {}
    
    mqt_baseline = localize_mqt(s3_mqt_file) \
        if s3_mqt_file is not None else {}

    if not qaf_baseline and not mqt_baseline:
        raise GearExecutionError("No records found in QAF or MQT baselines")

    curator = RegressionCurator(sdk_client=context.get_client(),
                                qaf_baseline=qaf_baseline,
                                mqt_baseline=mqt_baseline,
                                error_writer=error_writer)

    scheduler.apply(curator=curator)
