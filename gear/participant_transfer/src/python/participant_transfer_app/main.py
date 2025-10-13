"""Defines Manage Participant Transfer."""

import logging
from typing import List, Optional

from centers.nacc_group import NACCGroup
from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentError, TransferRecord
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectError
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
)
from participant_transfer_app.copy import CopyHelper
from participant_transfer_app.transfer import TransferProcessor

log = logging.getLogger(__name__)


def review_transfer_info(
    enroll_project: EnrollmentProject,
    ptid: str,
    admin_group: NACCGroup,
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

    if transfer_record.status not in ["approved", "partial"]:
        log.error(
            f"Transfer request for PTID {ptid} is not approved yet, "
            f"review this request and approve before initiating the transfer"
        )
        return None

    if transfer_record.previous_adcid is None:
        log.error(f"Missing previous ADCID in transfer request for PTID {ptid}")
        return None

    valid = True
    try:
        receiving_adcid = enroll_project.get_pipeline_adcid()
    except ProjectError as error:
        raise GearExecutionError(error) from error

    if transfer_record.center_identifiers.adcid != receiving_adcid:
        log.error(
            f"Mismatched ADCID {transfer_record.center_identifiers.adcid} in "
            f"transfer request for PTID {ptid}, "
            f"ADCID for project {enroll_project.group}/{enroll_project.label} "
            f"is {receiving_adcid}"
        )
        valid = False

    adcids_list = admin_group.get_form_ingest_adcids()
    if transfer_record.previous_adcid not in adcids_list:
        log.error(
            f"Invalid previous ADCID {transfer_record.previous_adcid} in "
            f"transfer request for PTID {ptid}"
        )
        valid = False

    return transfer_record if valid else None


def run(  # noqa: C901
    *,
    proxy: FlywheelProxy,
    admin_group: NACCGroup,
    enroll_project: EnrollmentProject,
    ptid: str,
    identifiers_repo: IdentifiersLambdaRepository,
    datatypes: List[str],
    copy_only: bool,
    dry_run: bool,
) -> bool:
    """Runs the Manage Participant Transfer process.

    Args:
        proxy: the proxy for the Flywheel instance
        admin_group: Admin group in Flywheel
        enroll_project: enrollment project with transfer info
        ptid: PTID to be transferred
        identifiers_repo: Identifiers lambda repository
        datatypes: List of datatypes to be transferred
        copy_only: No database update, only copy participant data.
                   Used when handling copy failure
        dry_run: Whether to do a dry run

    Returns:
        True if the transfer completed without any warnings, else False

    Raises:
        GearExecutionError: if any errors occur during transfer
    """

    transfer_record = review_transfer_info(
        enroll_project=enroll_project,
        ptid=ptid,
        admin_group=admin_group,
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

    oldadcid = transfer_record.previous_adcid
    prev_center = admin_group.get_center(oldadcid)
    if not prev_center or not prev_center.get_metadata():
        raise GearExecutionError(
            f"Cannot find center metadata for the previous center - ADCID: {oldadcid}"
        )

    if dry_run:
        log.info("Dry run only, exit")
        return True

    warnings: List[str] = []
    transfer_processor = TransferProcessor(
        enroll_project=enroll_project,
        transfer_record=transfer_record,
        identifiers_repo=identifiers_repo,
        warnings=warnings,
    )

    if copy_only:
        existing_identifier = transfer_processor.find_identifier_for_partial_transfer()
    else:
        existing_identifier = transfer_processor.find_identifier_record()

    if not existing_identifier:
        raise GearExecutionError(
            f"Failed to find valid identifier record for transfer request PTID {ptid} "
            f"in enrollment project {enroll_project.group}/{enroll_project.label}"
        )

    if not copy_only:
        if not transfer_processor.update_database(
            existing_identifier=existing_identifier
        ):
            raise GearExecutionError(
                "Failed to update identifiers database for the transfer request "
                f"PTID {ptid} in enrollment project "
                f"{enroll_project.group}/{enroll_project.label}"
            )

        if not transfer_processor.add_or_update_enrollment_records(
            prev_center=prev_center, prev_identifier=existing_identifier
        ):
            raise GearExecutionError(
                f"Failed to update enrollment records for transfer request PTID {ptid}"
            )

    copy_helper = CopyHelper(
        subject_label=existing_identifier.naccid,
        proxy=proxy,
        new_center=new_center,
        prev_center=prev_center,
        datatypes=datatypes,
        warnings=warnings,
    )

    if not copy_helper.copy_participant():
        transfer_processor.update_transfer_info(status="partial")
        raise GearExecutionError(
            "Error(s) occurred while copying data for "
            f"participant {existing_identifier.naccid}"
        )

    if not copy_helper.monitor_job_status():
        transfer_processor.update_transfer_info(status="partial")
        raise GearExecutionError(
            "One or more soft-copy jobs failed for "
            f"participant {existing_identifier.naccid}"
        )

    transfer_processor.update_transfer_info(status="completed")
    transfer_processor.update_transfer_request_qc_status()

    return not warnings
