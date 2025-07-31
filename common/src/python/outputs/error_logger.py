import logging
from datetime import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from configs.ingest_configs import ErrorLogTemplate
from dates.form_dates import DEFAULT_DATE_FORMAT, DEFAULT_DATE_TIME_FORMAT, convert_date
from flywheel.file_spec import FileSpec
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import FieldNames
from pydantic import ValidationError
from utils.decorators import api_retry

from outputs.error_models import FileErrorList, FileQCModel

log = logging.getLogger(__name__)

MetadataCleanupFlag = Literal["ALL", "GEAR", "NA"]


@api_retry
def update_file_info(file: FileEntry, custom_info: Dict[str, Any]):
    """Set custom info for the given file.

    Args:
        file: FileEntry object to set info
        custom_info: custom info dict,
                     any existing info under specified top-level key will be replaced

    Raise:
        ApiException: If failed to update custom info
    """

    # Note: have to use update_info() here for reset to take effect
    # Using update() will not delete any existing data
    file.update_info(custom_info)


def update_error_log_and_qc_metadata(
    *,
    error_log_name: str,
    destination_prj: ProjectAdaptor,
    gear_name: str,
    state: str,
    errors: FileErrorList,
    reset_qc_metadata: MetadataCleanupFlag = "NA",
) -> bool:
    """Update project level error log file and store error metadata in
    file.info.qc.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_name: gear that generated errors
        state: gear execution status [PASS|FAIL|NA]
        errors: list of error objects, expected to be JSON dicts
        reset_qc_metadata: flag to reset metadata from previous runs:
            ALL - clean all, set this for the first gear in submission pipeline.
            GEAR - reset only current gear metadata from previous runs.
            NA - do not reset (Default).

    Returns:
        bool: True if metadata update is successful, else False
    """

    # info: Dict[str, Any] = {"qc": {}}
    qc_info = FileQCModel(qc={})
    contents = ""

    current_log = destination_prj.get_file(error_log_name)
    # append to existing error details if any
    if current_log:
        current_log = current_log.reload()
        if current_log.info and "qc" in current_log.info and reset_qc_metadata != "ALL":
            try:
                qc_info = FileQCModel.model_validate(current_log.info, by_alias=True)
            except ValidationError as error:
                log.error(
                    "Error loading metadata for log file %s: %s", error_log_name, error
                )
                return False

        contents = (current_log.read()).decode("utf-8")  # type: ignore

    timestamp = (dt.now()).strftime(DEFAULT_DATE_TIME_FORMAT)
    contents += f"{timestamp} QC Status: {gear_name.upper()} - {state.upper()}\n"
    for qc_error in errors:
        contents += qc_error.model_dump_json(by_alias=True) + "\n"

    error_file_spec = FileSpec(
        name=error_log_name, contents=contents, content_type="text", size=len(contents)
    )
    try:
        destination_prj.upload_file(error_file_spec)
        destination_prj.reload()
        new_file = destination_prj.get_file(error_log_name)
    except ApiException as error:
        log.error(
            f"Failed to upload file {error_log_name} to "
            f"{destination_prj.group}/{destination_prj.label}: {error}"
        )
        return False

    error_list = errors.list()
    if reset_qc_metadata == "NA":  # do not reset
        file_errors = qc_info.get_errors(gear_name)
        error_list.extend(file_errors)

    qc_info.set_errors(gear_name=gear_name, status=state.upper(), errors=error_list)  # type: ignore

    try:
        update_file_info(file=new_file, custom_info=qc_info.model_dump(by_alias=True))
    except ApiException as error:
        log.error(
            "Error in setting QC metadata in file %s - %s",
            error_log_name,
            error,
        )
        return False

    return True


def get_error_log_name(
    *,
    module: str,
    input_data: Dict[str, Any],
    errorlog_template: Optional[ErrorLogTemplate] = None,
) -> Optional[str]:
    """Derive error log name based on visit data.

    Args:
        module: module label
        input_data: input visit record
        errorlog_template (optional): error log naming template for module

    Returns:
        str (optional): error log name or None
    """

    if not errorlog_template:
        errorlog_template = ErrorLogTemplate(
            id_field=FieldNames.PTID, date_field=FieldNames.DATE_COLUMN
        )

    ptid = input_data.get(errorlog_template.id_field)
    visitdate = input_data.get(errorlog_template.date_field)

    if not ptid or not visitdate:
        return None

    cleaned_ptid = ptid.strip().lstrip("0")
    normalized_date = convert_date(
        date_string=visitdate, date_format=DEFAULT_DATE_FORMAT
    )
    if not cleaned_ptid or not normalized_date:
        return None

    return (
        f"{cleaned_ptid}_{normalized_date}_{module.lower()}_"
        f"{errorlog_template.suffix}.{errorlog_template.extension}"
    )


def reset_error_log_metadata_for_gears(
    *, error_log_name: str, destination_prj: ProjectAdaptor, gear_names: List[str]
) -> None:
    """Reset error log file QC metadata in file.info.qc.<gear_name> for the
    specified gears.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_names: list of gears to clear qc metadata
    """
    current_log = destination_prj.get_file(error_log_name)
    if not current_log:
        return

    current_log = current_log.reload()
    if not current_log.info or not current_log.info.get("qc"):
        return

    # make sure to load the existing metadata first and then modify
    # update_file_info() will replace everything under the top-level key
    qc_info: Dict[str, Any] = current_log.info.get("qc", {})

    for gear_name in gear_names:
        qc_info.pop(gear_name, None)

    update_file_info(file=current_log, custom_info={"qc": qc_info})
