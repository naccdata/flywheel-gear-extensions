"""Defines Regression Curator."""
import csv
import json
import logging
from typing import List, MutableMapping

from curator.scheduling import ProjectCurationScheduler
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError
from outputs.errors import MPListErrorWriter
from s3.s3_client import S3BucketReader

from .regression_curator import RegressionCurator

log = logging.getLogger(__name__)


def localize_qaf(s3_qaf_file: str, keep_fields: List[str]) -> MutableMapping:
    """Localizes the QAF from S3 and converts to JSON. Only
    retains NACC* derived variables, visitdate, and
    fields specified by the keep_fields parameter.

    Args:
        s3_qaf_file: S3 QAF file to pull baseline from
        keep_fields: Additional fields to retain from the QAF
    """
    s3_qaf_file = s3_qaf_file.strip().replace('s3://', '')
    s3_bucket = s3_qaf_file.split('/')[:-1]
    filename = s3_qaf_file.split('/')[-1]

    s3_client = S3BucketReader.create_from_environment(s3_bucket)
    if not s3_client:
        raise GearExecutionError(
            f'Unable to access S3 bucket {rules_s3_bucket}')

    data = s3_client.read_data(filename=filename)
    reader = csv.DictReader(data)
    missing = []

    keep_fields.extend(['NACCID', 'VISITYR', 'VISITMO', 'VISITDAY'])

    for required in keep_fields:
        if required not in reader.fieldnames:
            missing.append(required)

    if missing:
        raise GearExecutionError(f'Requird fields not found in QAF header: {missing}') 

    baseline = {}
    for row in reader:
        naccid = row['NACCID']
        visitdate = f"{int(row['VISITYR']):02d}-{int(row['VISITMO']):02d}-{int(row['VISITDAY']):02d}"

        row_data = {'visitdate': visitdate}
        row_data.update({
            k.lower(): v for k, v in row.items()
            if k in keep_fields or k.startswith('NACC')
        })

        if naccid not in baseline:
            baseline[naccid] = []
        baseline.append(row_data)

    return baseline


def run(context: GearToolkitContext,
        s3_qaf_file: str,
        keep_fields: List[str],
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
