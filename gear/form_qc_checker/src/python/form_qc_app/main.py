"""Defines functions to carry out the data quality checks for the input form
data file.

Uses nacc-form-validator (https://github.com/naccdata/nacc-form-
validator) for validating the inputs.
"""

import json
import logging
from datetime import datetime, timezone
from json.decoder import JSONDecodeError
from typing import Any, Dict, Optional

from centers.nacc_group import NACCGroup
from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from flywheel import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearExecutionError,
    InputFileWrapper,
)
from keys.keys import DefaultValues, MetadataKeys
from nacc_common.error_models import FileErrorList, GearTags
from nacc_form_validator.quality_check import (
    QualityCheck,
    QualityCheckException,
)
from outputs.error_writer import ListErrorWriter
from redcap_api.redcap_connection import REDCapReportConnection
from s3.s3_bucket import S3BucketInterface

from form_qc_app.datastore import DatastoreHelper
from form_qc_app.definitions import DefinitionException, DefinitionsLoader
from form_qc_app.enrollment import CSVFileProcessor
from form_qc_app.error_info import REDCapErrorStore
from form_qc_app.processor import FileProcessor, JSONFileProcessor
from form_qc_app.validate import RecordValidator

log = logging.getLogger(__name__)


def update_input_file_qc_status(
    *,
    gear_context: GearToolkitContext,
    gear_name: str,
    input_wrapper: InputFileWrapper,
    file: FileEntry,
    qc_passed: bool,
    errors: Optional[FileErrorList] = None,
):
    """Write validation status to input file metadata and add gear tag.
    Detailed errors for each visit is recorded in the error log for the visit.

    Args:
        gear_context: Flywheel gear context
        gear_name: gear name
        file: Flywheel file object
        qc_passed: QC check passed or failed
        errors (optional): List of error metadata
    """

    status_str = "PASS" if qc_passed else "FAIL"

    gear_context.metadata.add_qc_result(
        input_wrapper.file_input,
        name="validation",
        state=status_str,
        data=errors.model_dump(by_alias=True) if errors is not None else None,
    )

    # set/update the validation timestamp in file.info
    timestamp = (datetime.now(timezone.utc)).strftime(DEFAULT_DATE_TIME_FORMAT)
    gear_context.metadata.update_file_metadata(
        input_wrapper.file_input,
        container_type=gear_context.destination["type"],
        info={MetadataKeys.VALIDATED_TIMESTAMP: timestamp},
    )

    gear_tags = GearTags(gear_name=gear_name)
    updated_tags = gear_tags.update_tags(tags=file.tags, status=status_str)
    gear_context.metadata.update_file_metadata(
        input_wrapper.file_input,
        tags=updated_tags,
        container_type=gear_context.destination["type"],
    )

    log.info("QC check status for file %s : %s [%s]", file.name, status_str, timestamp)

    return True


def load_supplement_input(
    supplement_input: InputFileWrapper,
) -> Optional[Dict[str, Any]]:
    with open(supplement_input.filepath, mode="r", encoding="utf-8-sig") as file_obj:
        try:
            input_data = json.load(file_obj)
        except (JSONDecodeError, TypeError) as error:
            log.error(
                "Failed to load supplement input file %s - %s",
                supplement_input.filename,
                error,
            )
            return None
    return input_data


def run(  # noqa: C901
    *,
    client_wrapper: ClientWrapper,
    input_wrapper: InputFileWrapper,
    s3_client: S3BucketInterface,
    admin_group: NACCGroup,
    gear_context: GearToolkitContext,
    form_project_configs: FormProjectConfigs,
    redcap_connection: Optional[REDCapReportConnection] = None,
    supplement_input: Optional[InputFileWrapper] = None,
):
    """Starts QC process for input file. Depending on the input file type calls
    the appropriate file processor.

    Args:
        client_wrapper: Flywheel SDK client wrapper
        input_wrapper: Gear input file wrapper
        s3_client: boto3 client for QC rules S3 bucket
        admin_group: Flywheel admin group
        gear_context: Flywheel gear context
        form_project_configs: module configurations
        redcap_connection (optional): REDCap project for NACC QC checks
        supplement_input (optional): input file for supplement module

    Raises:
        GearExecutionError if any problem occurs while validating input file
    """

    if not input_wrapper.file_input:
        raise GearExecutionError("form_data_file input not found")

    accepted_extensions = ["json", "csv"]
    file_type = input_wrapper.validate_file_extension(
        accepted_extensions=accepted_extensions
    )
    if not file_type:
        raise GearExecutionError(
            f"Unsupported input file type {input_wrapper.file_type}, "
            f"supported extension(s): {accepted_extensions}"
        )

    if file_type == "json":
        separator = "_"
        allowed = DefaultValues.MODULE_PATTERN.replace("_", "")
        split = None
    else:
        separator = "-"
        allowed = DefaultValues.MODULE_PATTERN
        split = "_"

    module = input_wrapper.get_module_name_from_file_suffix(
        separator=separator, allowed=allowed, split=split, extension=file_type
    )
    if not module:
        raise GearExecutionError(
            f"Failed to extract module information from file {input_wrapper.filename}"
        )
    module = module.upper()

    file_id = input_wrapper.file_id
    proxy = client_wrapper.get_proxy()
    try:
        file = proxy.get_file(file_id)
    except ApiException as error:
        raise GearExecutionError(f"Failed to find the input file: {error}") from error

    project = proxy.get_project_by_id(file.parents.project)
    if not project:
        raise GearExecutionError(
            f"Failed to find the project with ID {file.parents.project}"
        )
    project_adaptor = ProjectAdaptor(project=project, proxy=proxy)

    if (
        module not in form_project_configs.accepted_modules
        or not form_project_configs.module_configs.get(module)
    ):
        raise GearExecutionError(
            f"Failed to find the configurations for module {module}"
        )

    pk_field = form_project_configs.primary_key.lower()
    module_configs: ModuleConfigs = form_project_configs.module_configs.get(module)  # type: ignore
    date_field = module_configs.date_field
    strict = gear_context.config.get("strict_mode", True)

    error_writer = ListErrorWriter(
        container_id=file_id, fw_path=proxy.get_lookup_path(file)
    )

    rule_def_loader = DefinitionsLoader(
        s3_client=s3_client,
        error_writer=error_writer,
        module_configs=module_configs,
        project=project_adaptor,
        strict=strict,
    )

    error_store = REDCapErrorStore(redcap_con=redcap_connection)
    gear_name = gear_context.manifest.get("name", "form-qc-checker")

    file_processor: FileProcessor
    if file_type == "json":
        supplement_record = (
            load_supplement_input(supplement_input=supplement_input)
            if supplement_input
            else None
        )
        if (
            module_configs.supplement_module
            and module_configs.supplement_module.exact_match
            and not supplement_record
        ):
            raise GearExecutionError(
                f"Supplement {module_configs.supplement_module.label} "
                f"visit record is required to validate {module} visit"
            )

        file_processor = JSONFileProcessor(
            pk_field=pk_field,
            module=module,
            date_field=date_field,
            project=project_adaptor,
            error_writer=error_writer,
            form_configs=form_project_configs,
            gear_name=gear_name,
            supplement_data=supplement_record,
        )
    else:  # For enrollment form processing
        file_processor = CSVFileProcessor(
            pk_field=pk_field,
            module=module,
            date_field=date_field,
            project=project_adaptor,
            error_writer=error_writer,
            form_configs=form_project_configs,
            gear_name=gear_name,
        )

    input_data = file_processor.validate_input(input_wrapper=input_wrapper)

    if not input_data:
        update_input_file_qc_status(
            gear_context=gear_context,
            gear_name=gear_name,
            input_wrapper=input_wrapper,
            file=file,
            qc_passed=False,
            errors=error_writer.errors(),
        )
        return

    try:
        schema, codes_map = file_processor.load_schema_definitions(
            rule_def_loader=rule_def_loader, input_data=input_data
        )
    except DefinitionException as error:
        raise GearExecutionError(error) from error

    gid = file.parents.group
    try:
        adcid = project_adaptor.get_pipeline_adcid()
    except ProjectError as error:
        raise GearExecutionError(error) from error

    datastore = DatastoreHelper(
        pk_field=pk_field,
        proxy=proxy,
        adcid=adcid,
        module=module,
        group_id=gid,
        project=project_adaptor,
        admin_group=admin_group,
        module_configs=module_configs,
        form_project_configs=form_project_configs,
    )

    try:
        qual_check = QualityCheck(pk_field, schema, strict, datastore)  # type: ignore
    except QualityCheckException as error:
        raise GearExecutionError(f"Failed to initialize QC module: {error}") from error

    validator = RecordValidator(
        qual_check=qual_check,
        error_store=error_store,
        error_writer=error_writer,
        date_field=date_field,
        codes_map=codes_map,
    )

    valid = file_processor.process_input(validator=validator)

    update_input_file_qc_status(
        gear_context=gear_context,
        gear_name=gear_name,
        input_wrapper=input_wrapper,
        file=file,
        qc_passed=valid,
        errors=error_writer.errors(),
    )
