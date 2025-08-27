"""Module for processing a participant transfer."""

import logging
from datetime import datetime
from typing import Optional

from centers.center_group import CenterGroup
from enrollment.enrollment_project import EnrollmentProject, TransferInfo
from enrollment.enrollment_subject import EnrollmentSubject
from enrollment.enrollment_transfer import (
    EnrollmentError,
    EnrollmentRecord,
    TransferRecord,
)
from identifiers.identifiers_lambda_repository import (
    IdentifierRepositoryError,
    IdentifiersLambdaRepository,
)
from identifiers.identifiers_repository import IdentifierUpdateObject
from identifiers.model import CenterIdentifiers, IdentifierObject
from keys.keys import DefaultValues
from pydantic import ValidationError
from uploads.upload_error import UploaderError

log = logging.getLogger(__name__)


class TransferProcessor:
    """This class process a participant transfer request.

    - Updates identifiers database
    - Adds the subject to enrollment project
    - Updates subject enrollment metadata in both centers
    """

    def __init__(
        self,
        *,
        transfer_record: TransferRecord,
        enroll_project: EnrollmentProject,
        identifiers_repo: IdentifiersLambdaRepository,
    ) -> None:
        """Initialize the Transfer Processor."""
        self.__transfer_record = transfer_record
        self.__enroll_project = enroll_project
        self.__repo = identifiers_repo

    def __get_identifier_for_previous_center(self) -> Optional[IdentifierObject]:
        """Find the previous center's identifier record for this participant.

        Returns:
            IdentifierObject (optional): Identifier record if found, else None
        """
        old_adcid = self.__transfer_record.previous_identifiers.adcid  # type: ignore
        old_ptid = self.__transfer_record.previous_identifiers.ptid  # type: ignore

        if old_ptid == "unknown":
            if not self.__transfer_record.naccid:
                log.error(
                    "Cannot process the transfer request for "
                    f"PTID {self.__transfer_record.center_identifiers.ptid}, "
                    "no NACCID or previous PTID provided in the transfer record"
                )
                return None

            try:
                identifiers = self.__repo.list(naccid=self.__transfer_record.naccid)
            except (IdentifierRepositoryError, TypeError) as error:
                log.error(
                    f"Error in looking up identifier for "
                    f"NACCID {self.__transfer_record.naccid}: {error}"
                )
                return None

            if not identifiers:
                log.error(
                    "No identifier records found in the database for  "
                    f"NACCID {self.__transfer_record.naccid}"
                )
                return None

            for identifier in identifiers:
                if identifier.adcid == old_adcid:
                    return identifier

            log.error(
                f"No matching participant found for previous ADCID {old_adcid} "
                f"and NACCID {self.__transfer_record.naccid}"
            )
            return None

        try:
            return self.__repo.get(adcid=old_adcid, ptid=old_ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            log.error(
                f"Error in looking up NACCID for OLDADCID {old_adcid}, "
                f"OLDPTID {old_ptid}: {error}"
            )
            return None

    def find_identifier_record(self) -> Optional[IdentifierObject]:
        """Find the active identifier object for this participant.

        - check whether there is an active record for this participant in old center
        - check whether current ADCID, PTID has an active NACCID
        - check whether NACCID found in database matches with provided NACCID
        - check whether GUID found in database matches with provided GUID

        Returns:
            IdentifierObject (optional): Identifier object if active record found
        """
        adcid = self.__transfer_record.center_identifiers.adcid
        ptid = self.__transfer_record.center_identifiers.ptid
        old_adcid = self.__transfer_record.previous_identifiers.adcid  # type: ignore
        old_ptid = self.__transfer_record.previous_identifiers.ptid  # type: ignore

        curr_identifier = self.__get_identifier_for_previous_center()

        if not curr_identifier or not curr_identifier.active:
            log.error(
                "Failed to find an active identifier record in the database "
                f"for this participant for ADCID {old_adcid}"
            )
            return None

        if (
            self.__transfer_record.naccid
            and self.__transfer_record.naccid != curr_identifier.naccid
        ):
            log.error(
                f"NACCID mismatch: found in database {curr_identifier.naccid}, "
                f"provided in transfer record {self.__transfer_record.naccid}"
            )
            return None

        if (
            self.__transfer_record.guid
            and curr_identifier.guid
            and self.__transfer_record.guid != curr_identifier.guid
        ):
            log.error(
                f"GUID mismatch: found in database {curr_identifier.guid}, "
                f"provided in transfer record {self.__transfer_record.guid}"
            )
            return None

        try:
            identifier = self.__repo.get(adcid=adcid, ptid=ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            log.error(
                f"Error in looking up NACCID for ADCID {adcid}, PTID {ptid}: {error}"
            )
            return None

        if identifier:
            if identifier.active:
                log.error(f"Active NACCID already exist for ADCID {adcid}, PTID {ptid}")
                return None

            if identifier.naccid != curr_identifier.naccid:
                log.error(
                    f"NACCID mismatch: ID for ({adcid}, {ptid}): {identifier.naccid}, "
                    f"ID for ({old_adcid}, {old_ptid}): {curr_identifier.naccid}"
                )
                return None

            if (
                identifier.guid
                and curr_identifier.guid
                and identifier.guid != curr_identifier.guid
            ):
                log.error(
                    f"GUID mismatch: GUID for ({adcid}, {ptid}): {identifier.guid}, "
                    f"GUID for ({old_adcid}, {old_ptid}): {curr_identifier.guid}"
                )
                return None

        # update transfer record
        self.__transfer_record.naccid = curr_identifier.naccid
        self.__transfer_record.guid = curr_identifier.guid
        self.__transfer_record.previous_identifiers = CenterIdentifiers(
            adcid=curr_identifier.adcid, ptid=curr_identifier.ptid
        )

        return curr_identifier

    def update_database(self, current_identifier: IdentifierObject) -> bool:
        """Update the identifiers database.

        - Set previous center's record to inactive
        - Add/update current center's record (set to active)

        Args:
            current_identifier: current identifier object

        Returns:
            bool: True if database update successful, else False
        """

        success = False
        try:
            success = self.__repo.add_or_update(
                identifier=IdentifierUpdateObject.create_from_identifier(
                    identifier=current_identifier, active=False
                )
            )
        except (IdentifierRepositoryError, ValidationError) as error:
            log.error(
                "Error in updating identifiers database for "
                f"{current_identifier.adcid}, {current_identifier.ptid}: {error}"
            )
            return False

        if not success:
            return False

        try:
            new_identifier = self.__transfer_record.get_identifier_update_object(
                active=True
            )
            return self.__repo.add_or_update(identifier=new_identifier)
        except (IdentifierRepositoryError, ValidationError) as error:
            log.error(
                "Error in updating identifiers database for "
                f"{self.__transfer_record.center_identifiers.adcid}, "
                f"{self.__transfer_record.center_identifiers.ptid}: {error}"
            )
            return False

    def add_or_update_enrollment_records(self, prev_center: CenterGroup) -> bool:
        """Adds/updates the enrollment records in current and previous
        enrollment projects.

        Args:
            prev_center: Flywheel group for the previous center

        Returns:
            bool: True if add/update successful
        """

        record = EnrollmentRecord(
            center_identifier=self.__transfer_record.center_identifiers,
            guid=self.__transfer_record.guid,
            naccid=self.__transfer_record.naccid,
            start_date=self.__transfer_record.request_date,
        )

        assert record.naccid, "NACCID is required"

        # add a record to new center's enrollment project
        subject = self.__enroll_project.find_subject(label=record.naccid)
        if not subject:
            log.info(
                f"Adding new subject {record.naccid} to enrollment project "
                f"{self.__enroll_project.group}/{self.__enroll_project.label}"
            )
            enroll_subject = self.__enroll_project.add_subject(record.naccid)
        else:
            log.info(
                f"Subject with NACCID {record.naccid} exists in project "
                f"{self.__enroll_project.group}/{self.__enroll_project.label}"
            )
            enroll_subject = EnrollmentSubject.create_from(subject)

        try:
            enroll_subject.add_enrollment(record)
        except (UploaderError, ValidationError) as error:
            log.error(
                f"Failed to update enrollment info for {record.naccid} in "
                f"{self.__enroll_project.group}/{self.__enroll_project.label}: {error}"
            )
            return False

        # update the record in previous center's enrollment project
        prev_enroll_project = prev_center.find_project(DefaultValues.ENRL_PRJ_LABEL)
        if not prev_enroll_project:
            log.warning(
                "Failed to find enrollment project in previous center "
                f"{prev_center.label}, ADCID: {prev_center.adcid}"
            )
            return True  # returning true since this is possible

        prev_subject = prev_enroll_project.find_subject(label=record.naccid)
        if not prev_subject:
            log.warning(
                f"Participant {record.naccid} not found in enrollment project "
                f"{prev_enroll_project.group}/{prev_enroll_project.label}"
            )
            return True  # returning true since this is possible

        assert self.__transfer_record.previous_identifiers, "no previous_identifiers"

        prev_enroll_subject = EnrollmentSubject.create_from(prev_subject)

        updated_record = EnrollmentRecord(
            center_identifier=self.__transfer_record.previous_identifiers,
            guid=self.__transfer_record.guid,
            naccid=self.__transfer_record.naccid,
            start_date=self.__transfer_record.request_date,
            end_date=datetime.now(),
            status="transferred",
        )

        try:
            enroll_info = prev_enroll_subject.get_enrollment_info()
            if enroll_info:
                if enroll_info.status != "active":
                    log.error(
                        f"Participant {record.naccid} enrollment status != active in "
                        f"{prev_enroll_project.group}/{prev_enroll_project.label}"
                    )
                    return False

                updated_record.start_date = enroll_info.update_date

            prev_enroll_subject.update_enrollment(updated_record)
        except (EnrollmentError, UploaderError, ValidationError) as error:
            log.error(
                f"Failed to update enrollment info for {record.naccid} in "
                f"{prev_enroll_project.group}/{prev_enroll_project.label}: {error}"
            )
            return False

        return True

    def update_transfer_info(self) -> None:
        """Updates the transfer record status in enrollment project."""
        self.__transfer_record.status = "completed"
        self.__transfer_record.updated_date = datetime.now()
        transfer_info = TransferInfo(transfers={})
        transfer_info.add(self.__transfer_record)
        self.__enroll_project.add_or_update_transfers(transfers=transfer_info)
