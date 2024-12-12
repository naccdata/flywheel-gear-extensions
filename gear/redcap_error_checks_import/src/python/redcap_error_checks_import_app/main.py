"""Defines REDCap Import Error Checks."""
import json
import logging
from io import StringIO
from typing import Any, Dict, List

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import read_csv
from outputs.errors import ListErrorWriter
from redcap.redcap_connection import REDCapConnectionError
from redcap.redcap_project import REDCapProject
from s3.s3_client import S3BucketReader

from .error_check_csv_visitor import ErrorCheckCSVVisitor, ErrorCheckKey

log = logging.getLogger(__name__)


def load_error_check_csv(key: ErrorCheckKey,
                         file: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Load the error check CSV.

    Args:
        key: ErrorCheckKey containing details about the S3 key
        file: The S3 file object
    Returns:
        List of the validated and read in error checks.
    """
    error_writer = ListErrorWriter(container_id="local",
                                   fw_path="local")
    visitor = ErrorCheckCSVVisitor(key=key,
                                   error_writer=error_writer)

    data = StringIO(file['Body'].read().decode('utf-8-sig'))  # TODO: ideally want pure utf-8
    success = read_csv(input_file=data,
                       error_writer=error_writer,
                       visitor=visitor,
                       ignore_sniffer_errors=True)

    if not success:
        log.error(f"The following error occured while reading from {key.full_path}:")
        log.error(f"{[x['message'] for x in error_writer.errors()]}")
        return None

    if not visitor.validated_error_checks:
        log.error(f"No error checks found in {key.full_path}; invalid file?")
        return None

    return visitor.validated_error_checks


def run(*,
        proxy: FlywheelProxy,
        s3_bucket: S3BucketReader,
        redcap_project: REDCapProject,
        modules: List[str],
        fail_fast: bool = False
        ):
    """Runs the REDCAP Error Checks import process.

    Args:
        proxy: the proxy for the Flywheel instance
        s3_bucket: The S3BucketReader
        redcap_project: The QC Checks REDCapProject
        modules: List of modules to import error checks for
        fail_fast: Whether or not to fail fast on error
    """
    log.info("Running REDCAP error check import")
    bucket = s3_bucket.bucket_name
    file_objects = s3_bucket.read_directory("CSV")

    if not file_objects:
        log.error(f"No files found in {bucket}/CSV")
        return

    for key, file in file_objects.items():
        if not key.endswith('.csv'):
            continue

        error_key = ErrorCheckKey.create_from_key(key)
        if modules != ['all'] and error_key.module not in modules:
            continue

        # Load from files from S3
        log.info(f"Loading error checks from {bucket}/{error_key.full_path}")
        error_checks = load_error_check_csv(error_key, file)

        if not error_checks:
            if fail_fast:
                log.error("fail_fast set to True, halting execution")
                return
            else:
                log.info("Errors encountered, continuing to next file")
                continue

        if proxy.dry_run:
            log.info("DRY RUN: Skipping import.")
            continue

        # Upload to REDCap; import each record in JSON format
        try:
            num_records = redcap_project.import_records(json.dumps(error_checks),
                                                        data_format='json')
            log.info(f"Imported {num_records} records from {bucket}/{error_key.full_path}")
        except REDCapConnectionError as error:
            raise GearExecutionError(error.message) from error

        log.info(f"Successfully imported {bucket}/{error_key.full_path}!")

    log.info("Import complete!")