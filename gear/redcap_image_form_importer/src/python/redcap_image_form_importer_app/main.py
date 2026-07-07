"""Defines REDCap image form importer."""

import logging
import sys

from flywheel.models.container_output import ContainerOutput
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.flywheel_redcap_image_form import FlywheelREDCapImageForm
from gear_execution.gear_execution import GearExecutionError
from redcap_api.redcap_connection import REDCapConnection
from redcap_api.redcap_project import REDCapProject

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
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

def tag_fail(dry_run: bool, session: ContainerOutput, msg: str) -> None:
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
    "uploader_role",
    "uploader_rolex",
    "imagetype",
    "mpdtver",
    "clnaccidver",
    "clcnstver",
    "project",
    "protocol_confirm_scan",
    "protocol_confirm_cl",
    "file_reupload",
    "visit_code",
    "fundsource",
    "fundsourcex",
    "part_motion",
    "pass_criteria",
    "general_complete"
]

# Names of REDCap variables that are specific to PET sessions
pet_variables_to_import: list[str] = [
    "tracer",
    "tracerx",
    "tracer_dose_assay",
    "tracer_dose_time",
    "tracer_inj_time",
    "emission_start_time",
    "residual_dose_time",
    "pet_comments"
]

# Names of REDCap variables that are specific to MRI sessions
mri_variables_to_import: list[str] = [
    "mri_sedate",
    "mri_eyesopen",
    "mri_comments",
    "session_confirm"
]

def format_variables_for_session(
        redcap_variables_to_import: list,
        redcap_record: dict
    ) -> str:
    """Generates a formatted string for the specified variables that are
    available in the REDCap record.

    Args:
        redcap_variable: the name of the REDCap variable to check
        redcap_record: the session's record grabbed from REDCap

    Returns:
        A formatted string that defines the specified variables
    """
    string_to_return = ""
    for var in redcap_variables_to_import:
        if var in redcap_record:
            log.info(f'  {var}: "{redcap_record[var]}"')
            string_to_return += '"' + var + '":"' + redcap_record[var] + '"\n'
        else:
            log.info(f"  {var}: <missing>")
    return string_to_return

def verify_import_permitted(
        dry_run: bool,
        session: ContainerOutput,
        redcap_record: dict,
        redcap_variable: str,
        value_to_indicate_permitted
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
            f"Expected {redcap_variable} in REDCap record {redcap_record['record_id']}"
        )
    if redcap_record[redcap_variable] != str(value_to_indicate_permitted):
        tag_fail(
            dry_run,
            session,
            f"Expected {redcap_variable} to be '{value_to_indicate_permitted}' "
            f"but got '{redcap_record[redcap_variable]}'"
        )

def import_content_from_redcap_to_flywheel(
        dry_run: bool,
        redcap_record: dict,
        session: ContainerOutput,
        output_dir: str
) -> None:
    """Imports the given record from REDCap into the corresponding session in
    Flywheel.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        redcap_record: the session's record grabbed from REDCap
        session: target Flywheel session
        output_dir: directory to write output submission form to
    """
    content_to_import = format_variables_for_session(
        all_types_variables_to_import,
        redcap_record
    )

    if redcap_record["imagetype"] == 1: # PET
        content_to_import += format_variables_for_session(
            pet_variables_to_import,
            redcap_record
        )
    elif redcap_record["imagetype"] == 2: # MRI
        content_to_import += format_variables_for_session(
            mri_variables_to_import,
            redcap_record
        )

    log.info(f"Content to import for {session.label}_image-submission-form.json:\n"
             f"{content_to_import}")
    if dry_run:
        log.info("Dry run -- skipping import and tagging of session")
    else:
        out_json_name = (
            f"{output_dir}/{redcap_record['naccid']}"
            f"_{redcap_record['scandt']}_{session.label}_image-submission-form.json"
        )
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

def run(*,
        dry_run: bool,
        session_id: str,
        output_dir: str,
        redcap_con: REDCapConnection,
        proxy: FlywheelProxy):
    """Runs the REDCap Image Form Importer process, collecting the available
    information from REDCap to be imported into the Flywheel session.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session_id: Flywheel ID for the session
        output_dir: directory to write output submission form file to
        redcap_con: API connection to REDCap project
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
            f"Missing record_id in session {session.subject.label}::{session.label} " \
                f"({session.id})"
        )
    record_id = session.info["record_id"]

    redcap_proj = REDCapProject.create(redcap_con)
    log.info(
        f"Connected to REDCapProject with pid {redcap_proj.pid} "
        f"and title {redcap_proj.title}"
    )
    redcap_record = redcap_proj.export_records(record_ids = [record_id])
    if len(redcap_record) != 1:
        tag_fail(
            dry_run,
            session,
            f"Expected exactly one record for {record_id}, "
            f"but got {len(redcap_record)}"
        )
    redcap_record = redcap_record[0]

    # 2 for pass
    verify_import_permitted(dry_run, session, redcap_record, "pass_criteria", 2)

    # 2 for complete
    verify_import_permitted(dry_run, session, redcap_record, "general_complete", 2)

    fw_record = FlywheelREDCapImageForm(session, proxy)
    for var in fw_record.all_types_variables_to_check:
        if str(fw_record[var]) != redcap_record[var]:
            tag_fail(
                dry_run,
                session,
                f"Mismatch for {var}: FW gives '{fw_record[var]}' "
                f"but REDCap gives '{redcap_record[var]}'"
            )

    import_content_from_redcap_to_flywheel(dry_run, redcap_record, session, output_dir)
