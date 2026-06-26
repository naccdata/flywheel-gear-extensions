"""Defines REDCap Image Form Creator."""

import json
import logging
import re
from time import sleep
from typing import Any, Dict, NoReturn, Optional

from flywheel.models.container_output import ContainerOutput
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from redcap_api.redcap_connection import REDCapConnection
from redcap_api.redcap_project import REDCapProject

log = logging.getLogger(__name__)

pass_tag = "redcap-image-form-creator-PASS"
fail_tag = "redcap-image-form-creator-FAIL"


def tag_pass(session: ContainerOutput) -> None:
    if fail_tag in session.tags:
        session.delete_tag(fail_tag)
    if pass_tag not in session.tags:
        session.add_tag(pass_tag)


def tag_fail(dry_run: bool, session: ContainerOutput, msg: str) -> NoReturn:
    if not dry_run:
        if pass_tag in session.tags:
            session.delete_tag(pass_tag)
        if fail_tag not in session.tags:
            session.add_tag(fail_tag)
    raise GearExecutionError(msg)


######### BEGIN SECTION FOR COMMON

# keys are Flywheel's two-character modality
# values are NACC's three-character imagetype
imagetype_from_modality = {
    "PT": 1,  # 'PET'
    "MR": 2,  # 'MRI',
}

pet_tag_for_variable = {
    "tracer_dose_assay": "RadionuclideTotalDose",
    "tracer_inj_time": "RadiopharmaceuticalStartDateTime",
    "emission_start_time": "AcquisitionTime",
}


def find_flywheel_origin_user_id(
    dry_run: bool,
    session: ContainerOutput,
    flywheel_obj: FileEntry,
    proxy: FlywheelProxy,
) -> Optional[str]:
    match flywheel_obj.origin["type"]:
        case "user":
            return flywheel_obj.origin["id"]
        case "job":
            job = proxy.get_job_by_id(flywheel_obj.origin["id"])
            if job is None:
                tag_fail(
                    dry_run,
                    session,
                    f"Unable to determine uploader for object {flywheel_obj.id}",
                )
                return None
            try:
                return job["config"]["inputs"]["input-file"]["object"]["origin"]["id"]
            except (KeyError, TypeError, IndexError):
                tag_fail(
                    dry_run,
                    session,
                    f"Unable to determine uploader for object {flywheel_obj.id}",
                )
        case _:
            tag_fail(
                dry_run,
                session,
                f"Unable to determine uploader for object {flywheel_obj.id}",
            )


def inspect_acquisitions(  # noqa: C901
    dry_run: bool,
    session: ContainerOutput,
    session_info_to_import: Dict[str, Any],
    proxy: FlywheelProxy,
) -> None:
    def set_or_agree(key_to_set: str, val_to_set: Any, info_context: str):
        if key_to_set not in session_info_to_import:
            session_info_to_import[key_to_set] = val_to_set
        elif session_info_to_import[key_to_set] != val_to_set:
            tag_fail(
                dry_run,
                session,
                f'Expected "{session_info_to_import[key_to_set]}" not "{val_to_set}" '
                f"for {key_to_set} from {info_context}",
            )

    fw_mri_series = []
    for acq in session.acquisitions():
        log.info(f"  Found acquisition: {acq.label}")
        for file in acq.files:
            file = file.reload()  # needed to populate file.info
            set_or_agree(
                "uploader_email",
                find_flywheel_origin_user_id(dry_run, session, file, proxy),
                f'origin["id"] in {file.name}',
            )
            set_or_agree(
                "imagetype",
                imagetype_from_modality[file.modality],
                f"file.modality in {file.name}",
            )
            studydt = file.info["header"]["dicom"]["StudyDate"]
            studydt = studydt[:4] + "-" + studydt[4:6] + "-" + studydt[6:]
            set_or_agree(
                "scandt",
                studydt,
                f'file.info["header"]["dicom"]["StudyDate"] in {file.name}',
            )
            if file.modality == "PT":
                for pet_var, pet_tag in pet_tag_for_variable.items():
                    if pet_tag in file.info["header"]["dicom"]:
                        set_or_agree(
                            pet_var,
                            file.info["header"]["dicom"][pet_tag],
                            f'file.info["header"]["dicom"]["{pet_var}"] in {file.name}',
                        )
            elif file.modality == "MR":
                # file.classification options: Features, Intent, and Measurement
                fw_mri_series.append(
                    ",".join(
                        file.classification["Measurement"]
                        + sorted(file.classification["Features"], reverse=True)
                    )
                    + ":"
                    + file.info["header"]["dicom"]["SeriesDescription"]
                )
    if "scandt" not in session_info_to_import:
        tag_fail(dry_run, session, "No scandt found from any acquisition")
    if file.modality == "MR":
        session_info_to_import["fw_mri_series"] = ";".join(fw_mri_series)


# does not find or define record_id because record_id needs special treatment
def construct_session_info_for_redcap(
    dry_run: bool, session: ContainerOutput, proxy: FlywheelProxy
) -> Dict[str, Any]:
    fw_proj = proxy.get_container_by_id(session.project)

    if "pipeline_adcid" in fw_proj.info:
        adcid = fw_proj.info["pipeline_adcid"]
    else:
        tag_fail(
            dry_run,
            session,
            "Expected pipeline_adcid key in custom information "
            f"from project {fw_proj.label} for session {session.label}",
        )
    if not isinstance(adcid, int):
        tag_fail(
            dry_run, session, f"Expected adcid to be int, not {type(adcid)} for {adcid}"
        )

    subject = session.subject
    if "naccid" not in subject.info:
        tag_fail(dry_run, session, "Expected entry for naccid in subject.info")
    session_info_to_import = {
        "adcid": adcid,
        "fw_session_label": session.label,
        "fwid": session.id,
        "ptid": session.subject.label,
        "naccid": session.subject.info["naccid"],
        "scanstart": session.timestamp.strftime("%H:%M:%S")
        if session.timestamp
        else "",
    }

    inspect_acquisitions(dry_run, session, session_info_to_import, proxy)
    if "uploader_email" in session_info_to_import:
        user = proxy.find_user(session_info_to_import["uploader_email"])
        if user is None:
            tag_fail(
                dry_run,
                session,
                "Unable to determine uploader_fullname from "
                f"email {session_info_to_import['uploader_email']}",
            )
        else:
            session_info_to_import["uploader_fullname"] = (
                (user.firstname or "") + " " + (user.lastname or "")
            )
    else:
        tag_fail(
            dry_run, session, "Missing uploader_email after inspecting acquisitions"
        )

    return session_info_to_import


######### END SECTION FOR COMMON


def get_record_id_suffix(session: ContainerOutput, proxy: FlywheelProxy) -> int:
    record_id_pattern = re.compile("^IMG[0-9]{2}_[0-9]{6}")

    fw_project = proxy.get_container_by_id(session.project)

    record_id_suffix = 1
    for proj_ses in fw_project.sessions():
        if proj_ses.id == session.id:
            continue
        ses = proxy.get_container_by_id(
            proj_ses.id
        )  # custom info not populated from fw_project.sessions()
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


MAX_NEW_RECORD_ATTEMPTS = 4
MAX_PAUSES_FOR_OTHER_SESSION = 3


def generate_unique_record_id(  # noqa: C901
    dry_run: bool, session: ContainerOutput, proxy: FlywheelProxy, adcid: int
) -> Optional[str]:
    record_id = compose_record_id(dry_run, adcid, session, proxy)
    if dry_run:
        log.info(f"Dry run -- returning {record_id}")
        return record_id

    confirmed_record_id = False
    for i in range(MAX_NEW_RECORD_ATTEMPTS):
        fw_project = proxy.get_container_by_id(session.project)
        confirmed_record_id = True
        for proj_ses in fw_project.sessions():
            if proj_ses.id == session.id:
                continue
            ses = proxy.get_container_by_id(
                proj_ses.id
            )  # custom info not populated from fw_project.sessions()
            ses.reload()
            if "record_id" in ses.info and ses.info["record_id"] == record_id:
                log.info(
                    f"Conflict during pass {i + 1}/{MAX_NEW_RECORD_ATTEMPTS}"
                    f" in record_id {record_id}"
                    f" for session {ses.subject.label}::{ses.label}"
                    f" ({ses.id})"
                )
                if int(ses.id, 16) < int(session.id, 16):
                    record_id = compose_record_id(dry_run, adcid, session, proxy)
                    log.info(f"Trying new record_id {record_id}")
                    confirmed_record_id = False
                    break
                else:
                    for p in range(MAX_PAUSES_FOR_OTHER_SESSION):
                        log.info(
                            f"Waiting to see if {ses.id} will yield "
                            f"{record_id} ({p + 1}/{MAX_PAUSES_FOR_OTHER_SESSION})"
                        )
                        sleep(1.0)
                        ses = proxy.get_container_by_id(
                            ses.id
                        )  # reload() does not update ses.info['record_id']
                        if ses.info["record_id"] != record_id:
                            log.info(f"  ...session {ses.id} yielded.")
                            break
                    ses.reload()
                    if ses.info["record_id"] == record_id:
                        record_id = compose_record_id(dry_run, adcid, session, proxy)
                        log.info(f"  ...trying new record_id {record_id}")
                        confirmed_record_id = False
                        break

    if confirmed_record_id:
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
    session_info_to_import: Dict[str, Any],
    session: ContainerOutput,
    proxy: FlywheelProxy,
) -> None:
    record_id = generate_unique_record_id(
        dry_run, session, proxy, session_info_to_import["adcid"]
    )

    final_session_info_to_import = dict()
    final_session_info_to_import["record_id"] = record_id
    final_session_info_to_import.update(session_info_to_import)
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


def run(
    *,
    dry_run: bool,
    session_id: str,
    redcap_con: REDCapConnection,
    proxy: FlywheelProxy,
):
    """Runs the REDCap Image Form Creator process, collecting the available
    information from the uploaded imaging for the REDCap form.

    Args:
        session_id: Flywheel ID for the session
        redcap_con: API connection to REDCap project
        proxy: the proxy for the Flywheel instance
    """

    session = proxy.get_container_by_id(session_id)
    if session.container_type != "session":
        log.info(f"Looking for session container in parent of {session.container_type}")
        session = proxy.get_container_by_id(session.parents[0])
        if session.container_type != "session":
            log.info(
                f"Looking for session container in parent of {session.container_type}"
            )
            session = proxy.get_container_by_id(session.parents[0])
            if session.container_type != "session":
                raise GearExecutionError(
                    f"Expected session, not {session.container_type}"
                )
    if session.info.get("record_id"):
        log.info(f"Note previous record_id for session is {session.info['record_id']}")

    session_info_to_import = construct_session_info_for_redcap(dry_run, session, proxy)

    import_new_record_for_session(
        dry_run, redcap_con, session_info_to_import, session, proxy
    )
