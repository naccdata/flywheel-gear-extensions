"""Defines Manage Participant Transfer."""

import logging
from typing import List, Optional

from centers.nacc_group import NACCGroup
from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentError, TransferRecord
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from participant_transfer_app.copy import CopyHelper
from participant_transfer_app.transfer import TransferProcessor

log = logging.getLogger(__name__)


def review_transfer_info(
    enroll_project: EnrollmentProject, ptid: str, admin_group: NACCGroup
) -> Optional[TransferRecord]:
    """Reviews whether the requested transfer is in approved status.

    Args:
        enroll_project: Flywheel enrollment project with transfer info
        ptid: PTID to be transferred
        admin_group: Admin group in Flywheel

    Returns:
        TransferRecord (optional): TransferRecord if transfer is in approved status
    """

    try:
        transfer_info = enroll_project.get_transfer_info()
    except EnrollmentError as error:
        log.error(error)
        return None

    transfer_record = transfer_info.transfers.get(ptid)
    if not transfer_record:
        log.error(f"No transfer request found for PTID {ptid}")
        return None

    if transfer_record.status == "completed":
        log.error(f"Transfer request for PTID {ptid} is already completed")
        return None

    if transfer_record.status != "approved":
        log.error(
            f"Transfer request for PTID {ptid} is not approved yet, "
            f"review this request and approve before initiating the transfer"
        )
        return None

    if not transfer_record.previous_adcid:
        log.error(f"Missing previous ADCID in transfer request for PTID {ptid}")
        return None

    valid = True
    center_adcid = admin_group.get_adcid(enroll_project.group)
    if transfer_record.center_identifiers.adcid != center_adcid:
        log.error(
            f"Mismatched ADCID {transfer_record.center_identifiers.adcid} in "
            f"transfer request for PTID {ptid}, "
            f"ADCID for center {enroll_project.group} is {center_adcid}"
        )
        valid = False

    adcids_list = admin_group.get_adcids()
    if transfer_record.previous_adcid not in adcids_list:
        log.error(
            f"Invalid previous ADCID {transfer_record.previous_adcid} in "
            f"transfer request for PTID {ptid}"
        )
        valid = False

    return transfer_record if valid else None


def run(
    *,
    proxy: FlywheelProxy,
    admin_group: NACCGroup,
    enroll_project: EnrollmentProject,
    ptid: str,
    identifiers_repo: IdentifiersLambdaRepository,
    datatypes: List[str],
    sender_email: str,
    target_emails: List[str],
    dry_run: bool,
):
    """Runs the Manage Participant Transfer process.

    Args:
        proxy: the proxy for the Flywheel instance
        admin_group: Admin group in Flywheel
        enroll_project: enrollment project with transfer info
        ptid: PTID to be transferred
        identifiers_repo: Identifiers lambda repository
        datatypes: List of datatypes to be transferred
        sender_email: sender email address to send the transfer complete notification
        target_emails: The target email(s) that the notification to be delivered
        dry_run: Whether to do a dry run
    """

    transfer_record = review_transfer_info(
        enroll_project=enroll_project, ptid=ptid, admin_group=admin_group
    )

    if not transfer_record:
        raise GearExecutionError(
            f"Invalid/incomplete transfer information for PTID {ptid} "
            f"in enrollment project {enroll_project.group}/{enroll_project.label}. "
            "Please review the transfer metadata"
        )

    adcid = transfer_record.center_identifiers.adcid
    new_center = admin_group.get_center(adcid)
    if not new_center or not new_center.get_metadata():
        raise GearExecutionError(
            f"Cannot find center metadata for the new center - ADCID: {adcid}"
        )

    oldadcid = transfer_record.previous_identifiers.adcid  # type: ignore
    prev_center = admin_group.get_center(oldadcid)
    if not prev_center or not prev_center.get_metadata():
        raise GearExecutionError(
            f"Cannot find center metadata for the previous center - ADCID: {oldadcid}"
        )

    if dry_run:
        log.info("Dry run only, exit")
        return

    transfer_processor = TransferProcessor(
        enroll_project=enroll_project,
        transfer_record=transfer_record,
        identifiers_repo=identifiers_repo,
    )

    current_identifier = transfer_processor.find_identifier_record()
    if not current_identifier:
        raise GearExecutionError(
            f"Failed to find valid identifier record for transfer request PTID {ptid} "
            f"in enrollment project {enroll_project.group}/{enroll_project.label}"
        )

    if not transfer_processor.update_database(current_identifier=current_identifier):
        raise GearExecutionError(
            f"Failed to update identifiers database for transfer request PTID {ptid} "
            f"in enrollment project {enroll_project.group}/{enroll_project.label}"
        )

    if not transfer_processor.add_or_update_enrollment_records(prev_center=prev_center):
        raise GearExecutionError(
            f"Failed to update enrollment records for transfer request PTID {ptid}"
        )

    copy_helper = CopyHelper(
        subject_label=current_identifier.naccid,
        proxy=proxy,
        new_center=new_center,
        prev_center=prev_center,
    )

    if not copy_helper.copy_participant(datatypes=datatypes):
        raise GearExecutionError(
            "Error(s) occurred while copying data for "
            f"participant {current_identifier.naccid}"
        )

    if not copy_helper.monitor_job_status():
        raise GearExecutionError(
            "One or more soft-copy jobs failed for "
            f"participant {current_identifier.naccid}"
        )

    transfer_processor.update_transfer_info()

    # TODO: send email
