"""Module for processing a participant transfer."""

import logging
from datetime import datetime
from typing import Optional

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
from identifiers.model import IdentifierObject
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

        prev_identifier = self.__get_identifier_for_previous_center()

        if not prev_identifier or not prev_identifier.active:
            log.error(
                "Failed to find an active identifier record in the database "
                f"for this participant for ADCID {old_adcid}"
            )
            return None

        if (
            self.__transfer_record.naccid
            and self.__transfer_record.naccid != prev_identifier.naccid
        ):
            log.error(
                f"NACCID mismatch: found in database {prev_identifier.naccid}, "
                f"provided in transfer record {self.__transfer_record.naccid}"
            )
            return None

        if (
            self.__transfer_record.guid
            and prev_identifier.guid
            and self.__transfer_record.guid != prev_identifier.guid
        ):
            log.error(
                f"GUID mismatch: found in database {prev_identifier.guid}, "
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

            if identifier.naccid != prev_identifier.naccid:
                log.error(
                    f"NACCID mismatch: ID for ({adcid}, {ptid}): {identifier.naccid}, "
                    f"ID for ({old_adcid}, {old_ptid}): {prev_identifier.naccid}"
                )
                return None

            if (
                identifier.guid
                and prev_identifier.guid
                and identifier.guid != prev_identifier.guid
            ):
                log.error(
                    f"GUID mismatch: GUID for ({adcid}, {ptid}): {identifier.guid}, "
                    f"GUID for ({old_adcid}, {old_ptid}): {prev_identifier.guid}"
                )
                return None

        self.__transfer_record.naccid = prev_identifier.naccid
        self.__transfer_record.guid = prev_identifier.guid
        return prev_identifier

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
        except IdentifierRepositoryError as error:
            log.error(
                "Error in updating identifiers database for "
                f"{current_identifier.adcid}, {current_identifier.ptid}: {error}"
            )
            return False

        if not success:
            return False

        new_identifier = self.__transfer_record.get_identifier_update_object(
            active=True
        )
        try:
            return self.__repo.add_or_update(identifier=new_identifier)
        except IdentifierRepositoryError as error:
            log.error(
                "Error in updating identifiers database for "
                f"{new_identifier.adcid}, {new_identifier.ptid}: {error}"
            )
            return False

    def add_or_update_enrollment_records(self) -> bool:
        """Adds/updates the enrollment records in current and previous
        enrollment projects.

        Args:
            record: Enrollment record to be updated

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

        subject = self.__enroll_project.find_subject(label=record.naccid)
        try:
            if not subject:
                log.info(
                    f"Adding new subject {record.naccid} to enrollment project "
                    f"{self.__enroll_project.group}/{self.__enroll_project.label}"
                )
                enroll_subject = self.__enroll_project.add_subject(record.naccid)
                enroll_subject.add_enrollment(record)
            else:
                log.info(
                    f"Subject with NACCID {record.naccid} exists in project "
                    f"{self.__enroll_project.group}/{self.__enroll_project.label}"
                )
                enroll_subject = EnrollmentSubject.create_from(subject)
                enroll_subject.update_enrollment(record)
        except (EnrollmentError, UploaderError) as error:
            log.error(
                f"Failed to create/update enrollment record "
                f"for {record.naccid}: {error}"
            )
            return False

        # TODO: update the record in previous center's enrollment project
        return True

    def update_transfer_info(self) -> None:
        """Updates the transfer record status in enrollment project."""
        self.__transfer_record.status = "completed"
        self.__transfer_record.updated_date = datetime.now()
        transfer_info = TransferInfo(transfers={})
        transfer_info.add(self.__transfer_record)
        self.__enroll_project.add_or_update_transfers(transfers=transfer_info)
