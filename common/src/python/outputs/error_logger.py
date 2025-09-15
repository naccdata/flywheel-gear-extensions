import logging
from datetime import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from flywheel.file_spec import FileSpec
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from pydantic import ValidationError
from utils.decorators import api_retry

from outputs.error_models import FileErrorList, FileQCModel, QCStatus

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


def get_log_contents(log_file: FileEntry) -> str:
    """Returns contents of the log file.

    Decodes content as UTF-8

    Args:
      log_file: the file entry
    Return:
       the contents of the log_file
    """
    return log_file.read().decode("utf-8")


def get_log_qc_info(log_file: FileEntry) -> Optional[FileQCModel]:
    """Gets the file.info.qc object for the log file.

    Args:
      log_file: the file entry for the log file
    Returns:
      a QC model object for the log_file. None if the info object could not be parsed.
    """
    log_file = log_file.reload()
    if not log_file.info:
        return FileQCModel(qc={})
    if "qc" not in log_file.info:
        return FileQCModel(qc={})

    try:
        return FileQCModel.model_validate(log_file.info, by_alias=True)
    except ValidationError as error:
        log.error("Error loading metadata for log file %s: %s", log_file.name, error)
        return None


def create_log_entry(*, gear_name: str, state: str, errors: FileErrorList) -> str:
    """Creates a log entry as a string.

    A log entry consists of a time-stamped row that indicates the gear and the
    QC status.
    If the status is FAIL, the list of errors is serialized on subsequent rows.

    Args:
      gear_name: the gear name
      state: the QC status for the gear job
      errors: the list of QC errors
    Returns:
      the string representation for the QC log entry
    """
    timestamp = (dt.now()).strftime(DEFAULT_DATE_TIME_FORMAT)
    entry = f"{timestamp} QC Status: {gear_name.upper()} - {state.upper()}\n"
    for qc_error in errors:
        entry += qc_error.model_dump_json(by_alias=True) + "\n"
    return entry


def upload_log(
    *, project: ProjectAdaptor, filename: str, contents: str
) -> Optional[FileEntry]:
    """Uploads a file to the projects using the name and contents.

    Args:
      project: the project
      filename: the file name
      contents: the string of file contents
    Returns:
      the FileEntry for the file. None if the file could not be uploaded.
    """
    error_file_spec = FileSpec(
        name=filename, contents=contents, content_type="text", size=len(contents)
    )
    try:
        project.upload_file(error_file_spec)
        project.reload()
        return project.get_file(filename)
    except ApiException as error:
        log.error(
            f"Failed to upload file {filename} to "
            f"{project.group}/{project.label}: {error}"
        )
        return None


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
        state: gear execution status [PASS|FAIL|IN REVIEW|NA]
        errors: list of error objects, expected to be JSON dicts
        reset_qc_metadata: flag to reset metadata from previous runs:
            ALL - clean all, set this for the first gear in submission pipeline.
            GEAR - reset only current gear metadata from previous runs.
            NA - do not reset (Default).

    Returns:
        bool: True if metadata update is successful, else False
    """
    qc_info: Optional[FileQCModel] = FileQCModel(qc={})
    contents = ""

    current_log = destination_prj.get_file(error_log_name)
    # append to existing error details if any
    if current_log:
        if reset_qc_metadata != "ALL":
            qc_info = get_log_qc_info(current_log)

        contents = get_log_contents(current_log)

    if qc_info is None:
        return False

    contents += create_log_entry(
        gear_name=gear_name, state=state.upper(), errors=errors
    )

    new_file = upload_log(
        project=destination_prj, filename=error_log_name, contents=contents
    )
    if new_file is None:
        return False

    error_list = errors.list()
    if reset_qc_metadata == "NA":
        # extend existing errors with new errors. maintaining order
        file_errors = qc_info.get_errors(gear_name)
        file_errors.extend(error_list)
        error_list = file_errors

    qc_info.set_errors(
        gear_name=gear_name,
        status=state.upper(),  # type: ignore
        errors=error_list,
    )
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


def update_gear_qc_status(
    *,
    error_log_name: str,
    destination_prj: ProjectAdaptor,
    gear_name: str,
    status: QCStatus,
) -> None:
    """Updates the QC status in error log file (file.info.qc.<gear_name>) for
    the specified gear.

    Args:
        error_log_name: error log file name
        destination_prj: Flywheel project adaptor
        gear_name: gear to update the QC status
        status: new status
    """
    current_log = destination_prj.get_file(error_log_name)
    if not current_log:
        log.warning(
            f"Cannot find error log file {error_log_name} in "
            f"project {destination_prj.group}/{destination_prj.label}"
        )
        return

    qc_info = get_log_qc_info(current_log)
    if not qc_info:
        log.warning(f"QC info not found in error log file {error_log_name}")
        return

    gear_info = qc_info.get(gear_name=gear_name)
    if not gear_info:
        log.warning(
            f"QC info not found for gear {gear_name} in error log file {error_log_name}"
        )
        return

    gear_info.set_status(status)
    qc_info.set(gear_name=gear_name, gear_model=gear_info)
    update_file_info(file=current_log, custom_info=qc_info.model_dump(by_alias=True))


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
    if not current_log.info:
        return

    # make sure to load the existing metadata first and then modify
    # update_file_info() will replace everything under the top-level key
    qc_info: Dict[str, Any] = current_log.info.get("qc", {})
    if not qc_info:
        return

    for gear_name in gear_names:
        qc_info.pop(gear_name, None)

    update_file_info(file=current_log, custom_info={"qc": qc_info})
