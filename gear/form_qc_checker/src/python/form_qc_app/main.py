"""Defines functions to carry out the data quality checks for the input form
data file.

Uses nacc-form-validator (https://github.com/naccdata/nacc-form-
validator) for validating the inputs.
"""

import logging
from typing import Any, Dict, List, Optional

from centers.nacc_group import NACCGroup
from flywheel import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from keys.keys import DefaultValues, FieldNames
from nacc_form_validator.quality_check import (
    QualityCheck,
    QualityCheckException,
)
from outputs.errors import ListErrorWriter
from redcap.redcap_connection import REDCapReportConnection
from s3.s3_client import S3BucketReader

from form_qc_app.datastore import DatastoreHelper
from form_qc_app.definitions import DefinitionException, DefinitionsLoader
from form_qc_app.enrollment import CSVFileProcessor
from form_qc_app.error_info import REDCapErrorStore
from form_qc_app.processor import FileProcessor, JSONFileProcessor
from form_qc_app.validate import RecordValidator

log = logging.getLogger(__name__)


def update_input_file_qc_status(*,
                                gear_context: GearToolkitContext,
                                gear_name: str,
                                input_wrapper: InputFileWrapper,
                                file: FileEntry,
                                qc_passed: bool,
                                errors: Optional[List[Dict[str, Any]]] = None):
    """Write validation status to input file metadata and add gear tag.
    Detailed errors for each visit is recorded in the error log for the visit.

    Args:
        gear_context: Flywheel gear context
        gear_name: gear name
        file: Flywheel file object
        qc_passed: QC check passed or failed
        errors (optional): List of error metadata
    """

    status_str = 'PASS' if qc_passed else 'FAIL'

    gear_context.metadata.add_qc_result(input_wrapper.file_input,
                                        name='validation',
                                        state=status_str,
                                        data=errors)

    fail_tag = f'{gear_name}-FAIL'
    pass_tag = f'{gear_name}-PASS'
    new_tag = f'{gear_name}-{status_str}'

    if file.tags:
        if fail_tag in file.tags:
            file.delete_tag(fail_tag)
        if pass_tag in file.tags:
            file.delete_tag(pass_tag)

    # file.add_tag(new_tag)
    gear_context.metadata.add_file_tags(input_wrapper.file_input, tags=new_tag)

    log.info('QC check status for file %s : %s', file.name, status_str)
    return True


def validate_input_file_type(mimetype: str) -> Optional[str]:
    """Check whether the input file type is accepted.

    Args:
        mimetype: input file mimetype

    Returns:
        Optional[str]: If accepted file type, return the type, else None
    """
    if not mimetype:
        return None

    mimetype = mimetype.lower()
    if mimetype.find('json') != -1:
        return 'json'

    if mimetype.find('csv') != -1:
        return 'csv'

    return None


def run(  # noqa: C901
        *,
        client_wrapper: ClientWrapper,
        input_wrapper: InputFileWrapper,
        s3_client: S3BucketReader,
        admin_group: NACCGroup,
        gear_context: GearToolkitContext,
        redcap_connection: Optional[REDCapReportConnection] = None):
    """Starts QC process for input file. Depending on the input file type calls
    the appropriate file processor.

    Args:
        client_wrapper: Flywheel SDK client wrapper
        input_wrapper: Gear input file wrapper
        s3_client: boto3 client for QC rules S3 bucket
        admin_group: Flywheel admin group
        gear_context: Flywheel gear context
        redcap_connection (Optional): REDCap project for NACC QC checks

    Raises:
        GearExecutionError if any problem occurs while validating input file
    """

    if not input_wrapper.file_input:
        raise GearExecutionError('form_data_file input not found')

    file_type = validate_input_file_type(input_wrapper.file_type)
    if not file_type:
        raise GearExecutionError(
            f'Unsupported input file type {input_wrapper.file_type}')

    module = input_wrapper.get_module_name_from_file_suffix()
    if not module:
        raise GearExecutionError(
            f'Failed to extract module information from file {input_wrapper.filename}'
        )
    module = module.upper()

    file_id = input_wrapper.file_id
    proxy = client_wrapper.get_proxy()
    try:
        file = proxy.get_file(file_id)
    except ApiException as error:
        raise GearExecutionError(
            f'Failed to find the input file: {error}') from error

    project = proxy.get_project_by_id(file.parents.project)
    if not project:
        raise GearExecutionError(
            f'Failed to find the project with ID {file.parents.project}')

    legacy_label = gear_context.config.get('legacy_project_label',
                                           DefaultValues.LEGACY_PRJ_LABEL)
    pk_field = (gear_context.config.get('primary_key',
                                        FieldNames.NACCID)).lower()
    date_field = (gear_context.config.get('date_field',
                                          FieldNames.DATE_COLUMN)).lower()
    strict = gear_context.config.get("strict_mode", True)

    error_writer = ListErrorWriter(container_id=file_id,
                                   fw_path=proxy.get_lookup_path(file))

    rule_def_loader = DefinitionsLoader(s3_client=s3_client,
                                        strict=strict,
                                        error_writer=error_writer)

    error_store = REDCapErrorStore(redcap_con=redcap_connection)
    gear_name = gear_context.manifest.get('name', 'form-qc-checker')

    file_processor: FileProcessor
    if file_type == 'json':
        file_processor = JSONFileProcessor(pk_field=pk_field,
                                           module=module,
                                           date_field=date_field,
                                           project=ProjectAdaptor(
                                               project=project, proxy=proxy),
                                           error_writer=error_writer,
                                           gear_name=gear_name)
    else:  # For enrollment form processing
        file_processor = CSVFileProcessor(pk_field=pk_field,
                                          module=module,
                                          date_field=date_field,
                                          project=ProjectAdaptor(
                                              project=project, proxy=proxy),
                                          error_writer=error_writer,
                                          gear_name=gear_name)

    input_data = file_processor.validate_input(input_wrapper=input_wrapper)

    if not input_data:
        update_input_file_qc_status(gear_context=gear_context,
                                    gear_name=gear_name,
                                    input_wrapper=input_wrapper,
                                    file=file,
                                    qc_passed=False,
                                    errors=error_writer.errors())
        return

    try:
        schema, codes_map = file_processor.load_schema_definitions(
            rule_def_loader=rule_def_loader, input_data=input_data)
    except DefinitionException as error:
        raise GearExecutionError(error) from error

    gid = file.parents.group
    adcid = admin_group.get_adcid(gid)
    if adcid is None:
        raise GearExecutionError(f'Failed to find ADCID for group: {gid}')

    datastore = DatastoreHelper(pk_field=pk_field,
                                orderby=date_field,
                                proxy=proxy,
                                adcid=adcid,
                                group_id=gid,
                                project=project,
                                admin_group=admin_group,
                                legacy_label=legacy_label)

    try:
        qual_check = QualityCheck(pk_field, schema, strict, datastore)
    except QualityCheckException as error:
        raise GearExecutionError(
            f'Failed to initialize QC module: {error}') from error

    validator = RecordValidator(qual_check=qual_check,
                                error_store=error_store,
                                error_writer=error_writer,
                                codes_map=codes_map)

    valid = file_processor.process_input(validator=validator)

    update_input_file_qc_status(gear_context=gear_context,
                                gear_name=gear_name,
                                input_wrapper=input_wrapper,
                                file=file,
                                qc_passed=valid,
                                errors=error_writer.errors())
