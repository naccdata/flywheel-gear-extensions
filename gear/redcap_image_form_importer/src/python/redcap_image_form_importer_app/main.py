"""Defines REDCap image form importer."""

import json
import logging
from typing import NoReturn

from flywheel.models.container_output import ContainerOutput
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from redcap_api.redcap_connection import REDCapConnection
from redcap_api.redcap_module_connection import REDCapModuleConnection
from redcap_api.redcap_project import REDCapProject
from redcap_imaging_forms.image_submission_form import ImageSubmissionForm

log = logging.getLogger(__name__)

pass_tag = "redcap-image-form-importer-PASS"
fail_tag = "redcap-image-form-importer-FAIL"


def tag_pass(session: ContainerOutput) -> None:
    """Handles the gear's tagging when it has completed successfully.

    Args:
        session: target Flywheel session
    """
    if fail_tag in session.tags:
        session.delete_tag(fail_tag)
    if pass_tag not in session.tags:
        session.add_tag(pass_tag)


def tag_fail(dry_run: bool, session: ContainerOutput, msg: str) -> NoReturn:
    """Handles gear-related tagging upon failure and raises an error.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session: target Flywheel session
        msg: string that describes the failure reason

    Raises:
        GearExecutionError because the gear has failed
    """
    if not dry_run:
        if pass_tag in session.tags:
            session.delete_tag(pass_tag)
        if fail_tag not in session.tags:
            session.add_tag(fail_tag)
    raise GearExecutionError(msg)


# Names of REDCap variables that are common across session types
all_types_variables_to_import: list[str] = [
    "adcid",
    "clariti_edc_status",
    "file_reupload",
    "fundsource",
    "fundsourcex",
    "imagetype",
    "naccid",
    "part_motion",
    "pass_criteria",
    "project",
    "protocol_confirm_cl",
    "protocol_confirm_scan",
    "ptid",
    "record_id",
    "scandt",
    "scanstart",
    "session_confirm",
    "visit_code",
]

# Names of REDCap variables that are specific to PET sessions
pet_variables_to_import: list[str] = [
    "emission_start_time",
    "pet_comments",
    "residual_dose_time",
    "tracer",
    "tracer_dose_assay",
    "tracer_dose_time",
    "tracer_inj_time",
    "tracerx",
]

# Names of REDCap variables that are specific to MRI sessions
mri_variables_to_import: list[str] = [
    "mri_comments",
    "mri_eyesopen",
    "mri_sedate",
]


def format_variables_for_session(
    redcap_variables_to_import: list, redcap_record: dict[str, str]
) -> dict[str, str]:
    """Collects the specified variables that are available in the REDCap
    record.

    Args:
        redcap_variables_to_import: list of REDCap variable names to collect
        redcap_record: the session's record grabbed from REDCap

    Returns:
        A dict of variable name to value for variables present in the record
    """
    collected: dict[str, str] = {}
    for var in redcap_variables_to_import:
        if var in redcap_record:
            log.info(f'  {var}: "{redcap_record[var]}"')
            collected[var] = redcap_record[var]
        else:
            log.info(f"  {var}: <missing>")
    return collected


def verify_import_permitted(
    dry_run: bool,
    session: ContainerOutput,
    redcap_record: dict[str, str],
    redcap_variable: str,
    value_to_indicate_permitted,
) -> None:
    """Checks that the given variable has a value that permits continuing with
    import.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session: target Flywheel session
        redcap_record: the session's record grabbed from REDCap
        redcap_variable: the name of the REDCap variable to check
        value_to_indicated_permitted: the value that indicates import is permitted.

    Raises:
        GearExecutionError if a unique record_id cannot be secured
    """
    if redcap_variable not in redcap_record:
        tag_fail(
            dry_run,
            session,
            f"Expected {redcap_variable} in REDCap record {redcap_record['record_id']}",
        )
    if redcap_record[redcap_variable] != str(value_to_indicate_permitted):
        tag_fail(
            dry_run,
            session,
            f"Expected {redcap_variable} to be '{value_to_indicate_permitted}' "
            f"but got '{redcap_record[redcap_variable]}'",
        )


def import_content_from_redcap_to_flywheel(
    dry_run: bool,
    redcap_record: dict[str, str],
    session: ContainerOutput,
    output_dir: str,
) -> None:
    """Imports the given record from REDCap into the corresponding session in
    Flywheel.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        redcap_record: the session's record grabbed from REDCap
        session: target Flywheel session
        output_dir: directory to write output submission form to
    """
    content: dict[str, str] = {}
    content.update(
        format_variables_for_session(all_types_variables_to_import, redcap_record)
    )

    if redcap_record["imagetype"] == "1":  # PET
        content.update(
            format_variables_for_session(pet_variables_to_import, redcap_record)
        )
    elif redcap_record["imagetype"] == "2":  # MRI
        content.update(
            format_variables_for_session(mri_variables_to_import, redcap_record)
        )

    content_to_import = json.dumps(content, indent=4)

    log.info(
        f"Content to import for {session.label}_image-submission-form.json:\n"
        f"{content_to_import}"
    )
    if dry_run:
        log.info("Dry run -- skipping import and tagging of session")
    else:
        out_json_name = output_dir + "/"
        for file_name_key in ["naccid", "scandt"]:
            if redcap_record.get(file_name_key) is not None:
                if out_json_name[-1] != "/":
                    out_json_name += "_"
                out_json_name += redcap_record[file_name_key]
        out_json_name += f"_{session.label}_image-submission-form.json"
        log.info(f"Writing to '{out_json_name}'")
        with open(out_json_name, "w") as output_json:
            output_json.write(content_to_import)
        tag_pass(session)


def verify_flywheel_matches_redcap(
    dry_run: bool,
    session: ContainerOutput,
    fw_record: ImageSubmissionForm,
    redcap_record: dict[str, str],
) -> None:
    """Verifies that Flywheel session data matches the REDCap record.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session: target Flywheel session
        fw_record: form data collected from Flywheel
        redcap_record: the session's record from REDCap

    Raises:
        GearExecutionError on mismatch or missing data
    """
    fw_record_dict = fw_record.model_dump(exclude_none=True)
    for var in fw_record.required_fields:
        if (
            var == "redcap_data_access_group"
            and fw_record_dict.get(var) == ""
            and fw_record_dict.get("adcid") == 0
        ):
            log.info(f"Note: skipping agreement of {var} for test center")
            continue
        if var not in fw_record_dict:
            tag_fail(
                dry_run,
                session,
                f"Missing {var} from Flywheel session data",
            )
        if str(fw_record_dict[var]) != redcap_record[var]:
            tag_fail(
                dry_run,
                session,
                f"Mismatch for {var}: FW gives '{fw_record_dict[var]}' "
                f"but REDCap gives '{redcap_record[var]}'",
            )


def get_redcap_record(
    dry_run: bool,
    redcap_proj: REDCapProject,
    record_id: str,
    session: ContainerOutput,
) -> dict[str, str]:
    """Gets the REDCap record for the target record_id.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        redcap_proj: the REDCap project
        record_id: the target record identifier
        session: target Flywheel session

    Returns:
        The REDCap record
    """
    redcap_record_list = redcap_proj.export_records(record_ids=[record_id])
    if len(redcap_record_list) != 1:
        tag_fail(
            dry_run,
            session,
            f"Expected exactly one record for {record_id}, "
            f"but got {len(redcap_record_list)}",
        )
    redcap_record = redcap_record_list[0]
    if isinstance(redcap_record, str):
        tag_fail(
            dry_run, session, f"Expected dict from REDCap but got '{redcap_record}'"
        )
    assert isinstance(redcap_record, dict), (
        "variable redcap_record from REDCap must be a dict"
    )
    return redcap_record


def record_is_locked(redcap_lock_con: REDCapModuleConnection, record_id: str) -> bool:
    """Determines lock status for the target record.

    Args:
        redcap_lock_con: the connection to the REDCap module
        record_id: the target record identifier
    Returns:
        True if record is locked and False if it is unlocked
    """
    lock_data = {"record": record_id, "lock_record_level": "true"}
    lock_status_list = redcap_lock_con.post_module_request(
        action_page="status", data=lock_data
    )
    if not lock_status_list:
        return False
    if isinstance(lock_status_list, str):
        log.warning(
            f"Received '{lock_status_list}' when requesting status for {record_id}"
        )
        return False
    if len(lock_status_list) > 1:
        log.warning(
            f"Received multiple REDCap entries for {record_id}"
            " -- inspecting only the first"
        )
    if lock_status_list[0].get("locked"):
        return lock_status_list[0]["locked"] == "1"
    return False


def lock_redcap_record(redcap_lock_con: REDCapModuleConnection, record_id: str) -> None:
    """Locks the target record.

    Args:
        redcap_lock_con: the connection to the REDCap module
        record_id: the target record identifier
    Returns:
        True if record is locked and False if it is unlocked
    """
    log.info(f"Locking {record_id}")
    lock_data = {"record": record_id, "lock_record_level": "true"}
    lock_lock_list = redcap_lock_con.post_module_request(
        action_page="lock", data=lock_data
    )
    if not lock_lock_list:
        log.warning(f"Nothing returned from posting lock request for {record_id}")
    elif isinstance(lock_lock_list, str):
        log.warning(
            f"Received '{lock_lock_list}' when requesting status for {record_id}"
        )
    else:
        if len(lock_lock_list) > 1:
            log.warning(
                f"Received multiple REDCap entries for {record_id}"
                " -- inspecting only the first"
            )
        if lock_lock_list[0].get("locked"):
            if lock_lock_list[0]["locked"] != "1":
                log.warning(f"{record_id} still not locked")
        else:
            log.warning(f"Unable to confirm lock for {record_id}")


def run(
    *,
    dry_run: bool,
    lock_record: bool,
    session_id: str,
    output_dir: str,
    redcap_con: REDCapConnection,
    redcap_lock_con: REDCapModuleConnection | None,
    proxy: FlywheelProxy,
):
    """Runs the REDCap Image Form Importer process, collecting the available
    information from REDCap to be imported into the Flywheel session.

    Args:
        dry_run: flag for dry run (data collected but no modification/import or locking)
        session_id: Flywheel ID for the session
        output_dir: directory to write output submission form file to
        redcap_con: API connection to REDCap project
        redcap_lock_con: API connection to REDCap locking module for the project
        proxy: the proxy for the Flywheel instance

    Raises:
        GearExecutionError if critical information is not found
    """
    session = proxy.get_container_by_id(session_id)
    if session.container_type != "session":
        log.info(f"Looking for session in parent of {session.container_type}")
        session = proxy.get_container_by_id(session.parents[0])
        if session.container_type != "session":
            log.info(f"Looking for session in parent of {session.container_type}")
            session = proxy.get_container_by_id(session.parents[0])
            if session.container_type != "session":
                raise GearExecutionError(
                    f"Expected session, not {session.container_type}"
                )

    if "record_id" not in session.info:
        tag_fail(
            dry_run,
            session,
            f"Missing record_id in session {session.subject.label}::{session.label} "
            f"({session.id})",
        )
    record_id = session.info["record_id"]

    redcap_proj = REDCapProject.create(redcap_con)
    log.info(
        f"Connected to REDCapProject with pid {redcap_proj.pid} "
        f"and title {redcap_proj.title}"
    )
    redcap_record = get_redcap_record(dry_run, redcap_proj, record_id, session)

    # 2 for pass
    verify_import_permitted(dry_run, session, redcap_record, "pass_criteria", 2)

    # 2 for complete
    verify_import_permitted(
        dry_run, session, redcap_record, "image_submission_ecrf_complete", 2
    )

    if lock_record:
        assert redcap_lock_con is not None, (
            "REDCapModuleConnection redcap_lock_con must not be None in order to lock"
            "the record"
        )
        if record_is_locked(redcap_lock_con, record_id):
            log.info(f"REDCap record for {record_id} is already locked")
        elif dry_run:
            log.info(f"Skipping lock of record {record_id} because of dry run")
        else:
            lock_redcap_record(redcap_lock_con, record_id)

    fw_record = ImageSubmissionForm.from_session(session, proxy)
    verify_flywheel_matches_redcap(dry_run, session, fw_record, redcap_record)

    import_content_from_redcap_to_flywheel(dry_run, redcap_record, session, output_dir)
