"""Defines Regression Curator."""
import logging
from typing import List, MutableMapping

from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from outputs.errors import MPListErrorWriter
from s3.s3_client import S3BucketReader

from .regression_curator import RegressionCurator

log = logging.getLogger(__name__)


def process_header(header_line: str, keep_fields: List[str]) -> List[str]:
    """Process the header line.

    Args:
        header_line: Header line to process
        keep_fields: Required fields in the header.
    """
    header = header_line.split(',')
    missing = []
    for required in keep_fields:
        if required not in header:
            missing.append(required)

    if missing:
        raise GearExecutionError(
            f'Required fields not found in QAF header: {missing}')

    # make lowercase
    return [x.lower() for x in header]


def localize_qaf(s3_qaf_file: str, keep_fields: List[str]) -> MutableMapping:
    """Localizes the QAF from S3 and converts to JSON. Only retains NACC*
    derived variables, visitdate, and fields specified by the keep_fields
    parameter. Assumes no case-sensitivity and converts headers to lowercase.

    Args:
        s3_qaf_file: S3 QAF file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
    Returns:
        Baseline mapping from NACCID to list of entries from the QAF
    """
    s3_qaf_file = s3_qaf_file.strip().replace('s3://', '')
    s3_bucket = '/'.join(s3_qaf_file.split('/')[:-1])
    filename = s3_qaf_file.split('/')[-1]

    s3_client = S3BucketReader.create_from_environment(s3_bucket)
    if not s3_client:
        raise GearExecutionError(f'Unable to access S3 bucket {s3_bucket}')

    # the QAF is extremely large, so stream and process by line
    # by only retaining a subset of fields, should drastically reduce size
    body = s3_client.get_file_object(filename)['Body']
    header = None
    baseline: MutableMapping = {}

    for line, row in enumerate(body.iter_lines()):
        row = row.decode('utf-8')
        if not header:
            header = process_header(row, keep_fields)
            continue

        # convert row to dict
        row = row.split(',')
        if len(header) != len(row):
            raise GearExecutionError(
                f"Line {line} of the QAF does not match header length")

        row = {header[i]: row[i] for i in range(len(header))}

        # actually do the QAF processing now
        naccid = row['naccid']
        visitdate = (f"{int(row['visityr']):02d}-" +
                     f"{int(row['visitmo']):02d}-" +
                     f"{int(row['visitday']):02d}")

        row_data = {'visitdate': visitdate}
        row_data.update({
            k: v
            for k, v in row.items() if k in keep_fields or k.startswith('nacc')
        })

        if naccid not in baseline:
            baseline[naccid] = []
        baseline.append(row_data)

    return baseline


def run(context: GearToolkitContext, s3_qaf_file: str, keep_fields: List[str],
        scheduler: ProjectCurationScheduler,
        error_writer: MPListErrorWriter) -> None:
    """Runs the Attribute Curator process.

    Args:
        context: gear context
        s3_qaf_file: S3 QAF file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
        scheduler: Schedules the files to be curated
        error_writer: Multi-processing error writer
    """
    baseline = localize_qaf(s3_qaf_file, keep_fields)
    scheduler.apply(context=context,
                    curator_type=RegressionCurator,
                    baseline=baseline,
                    error_writer=error_writer)
