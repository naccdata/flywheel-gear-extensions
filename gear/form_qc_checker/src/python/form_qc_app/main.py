"""Defines functions to carry out the data quality checks for the input form
data file."""

import json
import logging
import sys
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional

from flywheel import Client
from flywheel_gear_toolkit import GearToolkitContext
from form_qc_app.error_info import ErrorComposer, REDCapErrorStore
from form_qc_app.flywheel_datastore import FlywheelDatastore
from form_qc_app.parser import Keys, Parser, ParserException
from outputs.errors import ListErrorWriter
from redcap.redcap_connection import REDCapReportConnection
from s3.s3_client import S3BucketReader
from validator.quality_check import QualityCheck, QualityCheckException

log = logging.getLogger(__name__)


def update_file_metadata(*, gear_context: GearToolkitContext, file_input: Any,
                         qc_status: bool, error_writer: ListErrorWriter):
    """Write error details to input file metadata and add gear tag.

    Args:
        gear_context: Flywheel gear context
        file_input: file input object from gear context
        qc_status: QC check passed or failed
        error_writer: error output writer
    """

    status_str = "PASS" if qc_status else "FAIL"
    tag = gear_context.config.get('tag', 'form-qc-checker')
    current_tags = gear_context.get_input_file_object_value(
        'form_data_file', 'tags')
    fail_tag = f'{tag}-FAIL'
    pass_tag = f'{tag}-PASS'
    new_tag = f'{tag}-{status_str}'

    if current_tags:
        if fail_tag in current_tags:
            current_tags.remove(fail_tag)
        if pass_tag in current_tags:
            current_tags.remove(pass_tag)
        current_tags.append(new_tag)
    else:
        current_tags = [new_tag]

    gear_context.metadata.add_qc_result(file_input,
                                        name='validation',
                                        state=status_str,
                                        data=error_writer.errors())

    gear_context.metadata.update_file(file_input, tags=current_tags)

    file_name = file_input['location']['name']
    log.info('QC check status for file %s : %s', file_name, status_str)


def validate_required_keys(*, keys: List[str], data: Dict[str, str]) -> bool:
    """Check whether all required keys are present in the input file.

    Args:
        keys: list of keys to validate
        data: input data to validate

    Returns:
        bool: returns True if all keys are present in data
    """

    if not data:
        log.error('Empty input file')
        return False

    present = True
    for key in keys:
        if key not in data:
            log.error('Missing required field %s in input data', key)
            present = False

    return present


def compose_error_metadata(
    *,
    sys_failure: bool,
    error_composer: ErrorComposer,
    error_tree: Optional[Dict[str, Any]],
    codes_map: Optional[Dict[str, Dict]],
):
    """Compose error metadata using validation errors and error code mapping.

    Args:
        sys_failure: True if any system errors occurred during validation
        error_compose: class to compose error metadata
        error_tree: dict like object containing validation error details
        codes_map: schema to map NACC QC check info to validation errors
    """
    if sys_failure:
        error_composer.compose_system_errors_metadata()
    elif codes_map and error_tree is not None:
        error_composer.compose_detailed_error_metadata(error_tree=error_tree,
                                                       err_code_map=codes_map)
    else:
        error_composer.compose_minimal_error_metadata()


# pylint: disable=(too-many-locals, too-many-statements)
def run(*,
        fw_client: Client,
        s3_client: S3BucketReader,
        gear_context: GearToolkitContext,
        redcap_connection: Optional[REDCapReportConnection] = None):
    """Starts QC process for form data input file. Load rule definitions from
    S3, read input data file, runs data validation, generate error report.

    Args:
        fw_client: the Flywheel SDK client
        s3_client: boto3 client for rules S3 bucket
        gear_context: Flywheel gear context
        redcap_connection (Optional): REDCap project for NACC QC checks
    """

    try:
        form_file_name = gear_context.get_input_filename('form_data_file')
    except ValueError as error:
        log.error('Gear input error for form_data_file: %s', error)
        sys.exit(1)

    if form_file_name is None:
        log.error('Missing input - form_data_file')
        sys.exit(1)

    file_input = gear_context.get_input('form_data_file')
    if file_input is None:
        log.error('Input file %s not found', form_file_name)
        sys.exit(1)

    file_id = file_input['object']['file_id']
    file = fw_client.get_file(file_id)

    try:
        with gear_context.open_input('form_data_file', 'r',
                                     encoding='utf-8') as form_file:
            form_data = json.load(form_file)
    except (FileNotFoundError, JSONDecodeError, TypeError,
            ValueError) as error:
        log.error('Failed to read the input file: %s', error)
        sys.exit(1)

    pk_field = (gear_context.config.get('primary_key', Keys.NACCID)).lower()
    keys = [pk_field, Keys.MODULE]
    if not validate_required_keys(keys=keys, data=form_data):
        sys.exit(1)

    s3_prefix = form_data[Keys.MODULE]
    if Keys.PACKET in form_data:
        s3_prefix = f'{s3_prefix}/{form_data[Keys.PACKET]}'

    parser = Parser(s3_client)
    try:
        schema = parser.download_rule_definitions(f'{s3_prefix}/rules/')
    except ParserException as error:
        log.error(error)
        sys.exit(1)

    try:
        codes_map: Optional[Dict[str,
                                 Dict]] = parser.download_rule_definitions(
                                     f'{s3_prefix}/codes/')  # type: ignore
    # TODO - validate code mapping schema and compare with error check schema
    except ParserException as error:
        log.warning(error)
        codes_map = None

    datastore = FlywheelDatastore(fw_client, file.parents.group,
                                  file.parents.project)

    error_store = REDCapErrorStore(redcap_con=redcap_connection)

    strict = gear_context.config.get("strict_mode", True)
    try:
        qual_check = QualityCheck(pk_field, schema, strict, datastore)
    except QualityCheckException as error:
        log.error('Error occured while initializing the QC module: %s', error)
        sys.exit(1)

    valid, sys_failure, dict_errors, error_tree = qual_check.validate_record(
        form_data)

    error_writer = ListErrorWriter(container_id=file_id)
    if not valid:
        error_messages = qual_check.validator.get_error_messages()
        error_composer = ErrorComposer(input_data=form_data,
                                       error_store=error_store,
                                       dict_errors=dict_errors,
                                       error_messages=error_messages,
                                       error_writer=error_writer)
        compose_error_metadata(
            sys_failure=sys_failure,
            error_composer=error_composer,
            error_tree=error_tree,  # type: ignore
            codes_map=codes_map)

    update_file_metadata(gear_context=gear_context,
                         file_input=file_input,
                         qc_status=valid,
                         error_writer=error_writer)
