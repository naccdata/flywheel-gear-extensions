"""Defines Manage Participant Transfer."""

import logging
from typing import Optional

from centers.nacc_group import NACCGroup
from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import TransferRecord
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository

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

    transfer_info = enroll_project.get_transfer_info()
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

    if (
        not transfer_record.previous_identifiers
        or transfer_record.previous_identifiers.ptid == "unknown"
    ):
        log.error(
            f"Missing or invalid previous_identifiers info in "
            f"transfer request for PTID {ptid}"
        )
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
    if transfer_record.previous_identifiers.adcid not in adcids_list:
        log.error(
            f"Invalid previous ADCID {transfer_record.previous_identifiers.adcid} in "
            f"transfer request for PTID {ptid}"
        )
        valid = False

    return transfer_record if valid else None


def run(
    *,
    admin_group: NACCGroup,
    enroll_project: EnrollmentProject,
    ptid: str,
    identifiers_repo: IdentifiersLambdaRepository,
    source_email: str,
    dry_run: bool,
):
    """Runs the Manage Participant Transfer process.

    Args:
        admin_group: Admin group in Flywheel
        enroll_project: enrollment project with transfer info
        ptid: PTID to be transferred
        identifiers_repo: Identifiers lambda repository
        source_email: sender email address to send the transfer complete notification
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

    if not transfer_processor.add_or_update_enrollment_records():
        raise GearExecutionError(
            f"Failed to update enrollment records for transfer request PTID {ptid}"
        )

    # TODO: soft link participant data from previous center to new center

    transfer_processor.update_transfer_info()

    # TODO: send email
