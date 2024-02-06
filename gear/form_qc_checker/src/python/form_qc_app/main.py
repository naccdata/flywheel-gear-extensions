"""Defines functions to carry out the data quality checks for the input form
data file."""

import json
import logging
import sys
from json.decoder import JSONDecodeError

from flywheel import Client
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from form_qc_app.error_report import ErrorReport
from form_qc_app.flywheel_datastore import FlywheelDatastore
from form_qc_app.parser import FormVars, Parser
from s3.s3_client import S3BucketReader
from validator.quality_check import QualityCheck, QualityCheckException

log = logging.getLogger(__name__)


def validate_parents(parents: dict[str, str], input_file: str) -> bool:
    """Validate Flywheel parent containers for input file.

    Args:
        parents (dict[str, str]): parent container info [name, id]
        input_file (str): form data input file

    Returns:
        bool: returns False if parent container info missing
    """

    if not parents:
        log.error('Parent containers not set for input file: %s', input_file)
        return False
    if 'group' not in parents:
        log.error('Missing group id for input file: %s', input_file)
        return False
    if 'project' not in parents:
        log.error('Missing project id for input file: %s', input_file)
        return False

    return True


def update_file_metadata(gear_context: GearToolkitContext, file_name: str,
                         status: str):
    """Add gear tag to input file.

    Args:
        gear_context (GearToolkitContext): Flywheel gear context
        file_name (str): Input file name
        status (str): QC check status
    """
    tag = gear_context.config.get('tag', 'form-qc-checker')
    current_tags = gear_context.get_input_file_object_value(
        'form_data_file', 'tags')
    fail_tag = f'{tag}-FAIL'
    pass_tag = f'{tag}-PASS'
    new_tag = f'{tag}-{status}'

    if current_tags:
        if status == "PASS" and fail_tag in current_tags:
            current_tags.remove(fail_tag)
        elif status == "FAIL" and pass_tag in current_tags:
            current_tags.remove(pass_tag)
        current_tags.append(new_tag)
    else:
        current_tags = [new_tag]

    gear_context.metadata.update_file(file_name, tags=current_tags)


def run(*, fw_client: Client, s3_client: S3BucketReader,
        gear_context: GearToolkitContext, proxy: FlywheelProxy):
    """Starts QC process for form data input file. Load rule definitions from
    S3, read input data file, runs data validation, generate error report.

    Args:
        fw_client: the Flywheel SDK client
        s3_client: boto3 client for rules S3 bucket
        gear_context: Flywheel gear context
        proxy: the proxy for the Flywheel instance
    """

    form_file_path = gear_context.get_input_path('form_data_file')
    parents = gear_context.get_input_file_object_value('form_data_file',
                                                       'parents')
    if not validate_parents(parents, form_file_path):
        sys.exit(1)

    try:
        with gear_context.open_input('form_data_file', 'r',
                                     encoding='utf-8') as form_file:
            form_data = json.load(form_file)
    except (FileNotFoundError, JSONDecodeError, TypeError,
            ValueError) as error:
        log.error('Failed to read the input file: %s', error)
        sys.exit(1)

    module = form_data['module']
    packet = form_data['packet']
    parser = Parser(s3_client)
    schema = parser.download_rule_definitions(f"{module}/{packet}/")
    if not schema:
        log.error('Empty validation schema, failed to load rule definitions.')
        sys.exit(1)

    pk_field = gear_context.config.get('primary_key', FormVars.NACCID)
    pk_field = pk_field.lower()
    if pk_field not in form_data:
        log.error('Missing required primary key field %s in form data file',
                  pk_field)
        sys.exit(1)

    datastore = FlywheelDatastore(fw_client, parents['group'],
                                  parents['project'])

    strict = gear_context.config.get("strict_mode", True)
    try:
        qual_check = QualityCheck(pk_field, schema, strict, datastore)
    except QualityCheckException as error:
        log.error('Error occured while initializing the QC module: %s', error)
        sys.exit(1)

    valid, dict_erros = qual_check.validate_record(form_data)
    form_file_name = gear_context.get_input_filename('form_data_file')
    if not valid:
        error_report = ErrorReport(form_file_name)
        error_report.compose_error_report_for_visit(form_data, dict_erros)
        log.info(dict_erros)

    status = "PASS" if valid else "FAIL"
    update_file_metadata(gear_context, form_file_name, status)

    log.info('QC check status for file %s : %s', form_file_path, status)
