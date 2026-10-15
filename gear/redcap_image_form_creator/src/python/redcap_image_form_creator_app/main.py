"""Defines REDCap Image Form Creator."""

import json
import logging
import re
from time import sleep
from typing import NoReturn, Optional

from flywheel.models.container_output import ContainerOutput
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from redcap_api.redcap_connection import REDCapConnection
from redcap_api.redcap_project import REDCapProject
from redcap_imaging_forms.image_submission_form import ImageSubmissionForm

log = logging.getLogger(__name__)

pass_tag = "redcap-image-form-creator-PASS"
fail_tag = "redcap-image-form-creator-FAIL"


def tag_pass(session: ContainerOutput) -> None:
    """Handles the gear's tagging when it has completed successfully.

    Args:
        session: target Flywheel session
    """

    if fail_tag in session.tags:
        session.delete_tag(fail_tag)
    if pass_tag not in session.tags:
        session.add_tag(pass_tag)


def tag_fail(dry_run: bool, session: ContainerOutput | None, msg: str) -> NoReturn:
    """Handles gear-related tagging upon failure and exits.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session: target Flywheel session
        msg: string that describes the failure reason
    """

    if not dry_run and session is not None:
        if pass_tag in session.tags:
            session.delete_tag(pass_tag)
        if fail_tag not in session.tags:
            session.add_tag(fail_tag)
    log.error(msg)
    exit(1)


def get_record_id_suffix(session: ContainerOutput, proxy: FlywheelProxy) -> int:
    """Determines the lowest suffix (>=1) that is greater than all others.

    Iterates all sessions in the project, making one API call per session
    to fetch custom info. This is O(n) in project size; expected to be
    acceptable for imaging projects with tens to low hundreds of sessions.

    Args:
        session: target Flywheel session
        proxy: FlywheelProxy to check for uniqueness of record_id on Flywheel

    Returns:
        The next unused record_id suffix
    """

    record_id_pattern = re.compile("^IMG[0-9]{2}_[0-9]{6}")

    fw_project = proxy.get_container_by_id(session.project)

    record_id_suffix = 1
    for proj_ses in fw_project.sessions():
        if proj_ses.id == session.id:
            continue

        # session's custom info not populating if
        # grabbed directly from fw_project.sessions()
        ses = proxy.get_container_by_id(proj_ses.id)
        ses.reload()
        if "record_id" in ses.info:
            existing_record_id = ses.info["record_id"]
            if record_id_pattern.match(existing_record_id):
                existing_suffix = int(existing_record_id[-6:].lstrip("0"))
                if record_id_suffix <= existing_suffix:
                    record_id_suffix = existing_suffix + 1
            else:
                log.info(f"  Ignoring nonconforming record_id {existing_record_id}")

    return record_id_suffix


def compose_record_id(
    dry_run: bool, adcid: int, session: ContainerOutput, proxy: FlywheelProxy
) -> str:
    """Composes the REDCap record_id in the format IMGSS_XXXXXX, where SS is
    the site code (adcid) and the 6-digit suffix XXXXXX is different than the
    others within the Flywheel project.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        adcid: integer that identifies the ADC
        session: target Flywheel session
        proxy: FlywheelProxy to check for uniqueness of record_id on Flywheel

    Returns:
        The formatted string for record_id
    """

    composed_id = (
        "IMG"
        + str(adcid).zfill(2)
        + "_"
        + str(get_record_id_suffix(session, proxy)).zfill(6)
    )
    if not dry_run:
        session.update_info({"record_id": composed_id})
        session = proxy.get_container_by_id(session.id)
    return composed_id


# maximum attempts to generate a new record if the current attempt fails
MAX_NEW_RECORD_ATTEMPTS = 4

# maximum number of attempts to pause and see if the other session will yield
MAX_PAUSES_FOR_OTHER_SESSION = 3


def ensure_record_id_is_unique(
    dry_run: bool,
    session: ContainerOutput,
    proxy: FlywheelProxy,
    adcid: int,
    record_id: str,
) -> bool:
    """Ensures record_id is unique if not a dry run; tries to resolve possible
    collisions from simultaneous new sessions by waiting for other sessions to
    yield the record_id or by changing its own record_id.

        Args:
            dry_run: flag for dry run (data collected but no modifications)
            session: target Flywheel session
            proxy: FlywheelProxy to check for uniqueness of record_id on Flywheel
            adcid: integer that identifies the ADC
            record_id: given initial record_id, but could be modified if not a dry
    run

        Returns:
            boolean indicating whether the record_id could be confirmed to be
            unique
    """

    able_to_confirm_record_id = False
    for i in range(MAX_NEW_RECORD_ATTEMPTS):
        fw_project = proxy.get_container_by_id(session.project)
        able_to_confirm_record_id = True
        for proj_ses in fw_project.sessions():
            if proj_ses.id == session.id:
                continue

            # session's custom info not populating if grabbed
            # directly from fw_project.sessions()
            ses = proxy.get_container_by_id(proj_ses.id)
            ses.reload()
            if ses.info.get("record_id") == record_id:
                log.info(
                    f"Conflict during pass {i + 1}/{MAX_NEW_RECORD_ATTEMPTS}"
                    f" in record_id {record_id}"
                    f" for session {ses.subject.label}::{ses.label}"
                    f" ({ses.id})"
                )
                if int(ses.id, 16) < int(session.id, 16):
                    # Deterministic tiebreaker: the session with the higher
                    # hex ID yields by picking a new record_id; the lower
                    # hex ID waits. This ensures exactly one of two concurrent
                    # sessions will back off without coordination.
                    record_id = compose_record_id(dry_run, adcid, session, proxy)
                    log.info(f"Trying new record_id {record_id}")
                    able_to_confirm_record_id = False
                    break
                else:
                    for p in range(MAX_PAUSES_FOR_OTHER_SESSION):
                        log.info(
                            f"Waiting to see if {ses.id} will yield "
                            f"{record_id} ({p + 1}/{MAX_PAUSES_FOR_OTHER_SESSION})"
                        )
                        sleep(1.0)
                        # reload() does not update ses.info["record_id"],
                        # so get the fresh container again
                        ses = proxy.get_container_by_id(ses.id)
                        if ses.info["record_id"] != record_id:
                            log.info(f"  ...session {ses.id} yielded.")
                            break
                    ses.reload()
                    if ses.info["record_id"] == record_id:
                        record_id = compose_record_id(dry_run, adcid, session, proxy)
                        log.info(f"  ...trying new record_id {record_id}")
                        able_to_confirm_record_id = False
                        break
    return able_to_confirm_record_id


def generate_unique_record_id(
    dry_run: bool, session: ContainerOutput, proxy: FlywheelProxy, adcid: int
) -> Optional[str]:
    """Generates a unique REDCap record_id for the session; exits if a unique
    record_id cannot be secured.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session: target Flywheel session
        proxy: FlywheelProxy to check for uniqueness of record_id on Flywheel
        adcid: integer that identifies the ADC

    Returns:
        The unique record_id (confirmed if not a dry run)
    """

    record_id = compose_record_id(dry_run, adcid, session, proxy)
    if dry_run:
        log.info(f"Dry run -- returning {record_id}")
        return record_id

    if ensure_record_id_is_unique(dry_run, session, proxy, adcid, record_id):
        return record_id

    tag_fail(
        dry_run,
        session,
        "Unable to secure new unique record_id "
        f"after {MAX_NEW_RECORD_ATTEMPTS} attempt(s)",
    )


def import_new_record_for_session(
    dry_run: bool,
    redcap_con: REDCapConnection,
    session_info_to_import: ImageSubmissionForm,
    session: ContainerOutput,
    proxy: FlywheelProxy,
) -> None:
    """Imports the session's information into a new REDCap record; exits if a
    unique record_id cannot be secured.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        redcap_con: connection for recap_project
        session_info_to_import: dict-style information for REDCap form
        session: target Flywheel session
        proxy: FlywheelProxy to check for uniqueness of record_id on Flywheel
    """

    assert session_info_to_import.adcid is not None
    record_id = generate_unique_record_id(
        dry_run, session, proxy, session_info_to_import.adcid
    )
    final_session_info_to_import: dict = {"record_id": record_id}
    final_session_info_to_import.update(
        session_info_to_import.model_dump(exclude_none=True)
    )
    log.info("final session_info_to_import:")
    for key, val in final_session_info_to_import.items():
        log.info(f"\t{key}: {val}")

    redcap_proj = REDCapProject.create(redcap_con)
    log.info(
        f"Connected to REDCapProject with pid {redcap_proj.pid} "
        f"and title {redcap_proj.title}"
    )

    if record_id:
        if dry_run:
            log.info(
                f"Dry run -- skipping tag and import to REDCap {session_info_to_import}"
            )
        else:
            redcap_proj.import_records(json.dumps([final_session_info_to_import]))
            tag_pass(session)
    else:
        tag_fail(dry_run, session, "Unable to generate unique new record_id")


def get_session_container(
    dry_run: bool, session_id: str, proxy: FlywheelProxy
) -> ContainerOutput:
    """Finds the associated session for the gear run.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session_id: Flywheel ID for the session
        proxy: the proxy for the Flywheel instance

    Returns: the associated session container
    """

    session = proxy.get_container_by_id(session_id)
    if session.container_type != "session":
        if session.parents.get("project") is None:
            tag_fail(dry_run, None, f"Expected session, not {session.container_type}")
        log.info(f"Looking for session container in parent of {session.container_type}")
        session = proxy.get_container_by_id(session.parents[0])
        if session.container_type != "session":
            log.info(
                f"Looking for session container in parent of {session.container_type}"
            )
            session = proxy.get_container_by_id(session.parents[0])
            if session.container_type != "session":
                tag_fail(
                    dry_run, None, f"Expected session, not {session.container_type}"
                )
    return session


def run(
    *,
    dry_run: bool,
    session_id: str,
    redcap_con: REDCapConnection,
    proxy: FlywheelProxy,
):
    """Runs the REDCap Image Form Creator process, collecting the available
    information from the uploaded image on Flywheel to be uploaded to the
    REDCap image form; exits if critical information is not found or the new
    record_id cannot be assigned.

    Args:
        dry_run: flag for dry run (data collected but no modifications)
        session_id: Flywheel ID for the session
        redcap_con: API connection to REDCap project
        proxy: the proxy for the Flywheel instance
    """

    session = get_session_container(dry_run, session_id, proxy)
    if session.info.get("record_id"):
        log.info(f"Note previous record_id for session is {session.info['record_id']}")

    session_info_to_import = ImageSubmissionForm.from_session(session, proxy)
    conflicts = session_info_to_import.get_conflicts()
    if conflicts:
        for field_name, reason in conflicts.items():
            log.warning(f"conflict in {field_name}: {reason}")
    missing_fields = session_info_to_import.check_required_fields()
    if missing_fields:
        for field_name in missing_fields:
            log.warning(f"missing {field_name}")
    if conflicts or missing_fields:
        tag_fail(
            dry_run,
            session,
            f"missing/conflicting information for {session.label} ({session.id})",
        )

    import_new_record_for_session(
        dry_run, redcap_con, session_info_to_import, session, proxy
    )
