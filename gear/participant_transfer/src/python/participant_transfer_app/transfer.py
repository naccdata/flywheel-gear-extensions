"""Module for processing a participant transfer."""

import logging
from datetime import datetime
from typing import Optional

from enrollment.enrollment_project import EnrollmentProject, TransferInfo
from enrollment.enrollment_transfer import EnrollmentRecord, TransferRecord
from identifiers.identifiers_lambda_repository import (
    IdentifierRepositoryError,
    IdentifiersLambdaRepository,
)
from identifiers.model import (
    IdentifierObject,
    IdentifierUpdateObject,
)

log = logging.getLogger(__name__)


class TransferProcessor:
    """This class process a participant transfer request.

    - Updates identifiers database
    - Adds the subject to enrollment project
    - Soft link participant data from previous center to new center
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

    def find_identifier_record(self) -> Optional[IdentifierObject]:
        """Find the identifier object corresponding to the OLDADCID, OLDPTID.

        - validates whether there is an active NACCID for OLDADCID, OLDPTID
        - compare with NACCID provided in transfer request
        - check whether current ADCID, PTID has an inactive NACCID
        - check whether GUID found in database matches with provided GUID

        Returns:
            IdentifierObject (optional): True if NACCID and GUID is valid, else False
        """
        adcid = self.__transfer_record.center_identifiers.adcid
        ptid = self.__transfer_record.center_identifiers.ptid
        old_adcid = self.__transfer_record.previous_identifiers.adcid  # type: ignore
        old_ptid = self.__transfer_record.previous_identifiers.ptid  # type: ignore

        try:
            prev_identifier = self.__repo.get(adcid=old_adcid, ptid=old_ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            log.error(
                f"Error in looking up NACCID for OLDADCID {old_adcid}, "
                f"OLDPTID {old_ptid}: {error}"
            )
            return None

        if not prev_identifier or not prev_identifier.active:
            log.error(
                f"Active NACCID not found for OLDADCID {old_adcid}, OLDPTID {old_ptid}"
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

    def update_database(
        self, current_identifier: IdentifierObject
    ) -> Optional[EnrollmentRecord]:
        """Update the identifiers database.

        - Set previous center's record to inactive
        - Add/update current center's record (set to active)

        Args:
            current_identifier: current identifier object

        Returns:
            EnrollmentRecord (optional): if database update successful, else None
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
            return None

        if not success:
            return None

        new_identifier = IdentifierUpdateObject.create_from_transfer_record(
            transfer_record=self.__transfer_record, active=True
        )
        try:
            success = self.__repo.add_or_update(identifier=new_identifier)
        except IdentifierRepositoryError as error:
            log.error(
                "Error in updating identifiers database for "
                f"{new_identifier.adcid}, {new_identifier.ptid}: {error}"
            )
            return None

        if not success:
            return None

        return EnrollmentRecord(
            center_identifier=self.__transfer_record.center_identifiers,
            guid=self.__transfer_record.guid,
            naccid=self.__transfer_record.naccid,
            start_date=self.__transfer_record.request_date,
        )

    def add_enrollment_record(self, record: EnrollmentRecord) -> bool:
        """_summary_

        Args:
            record (EnrollmentRecord): _description_

        Returns:
            bool: _description_
        """
        assert record.naccid, "NACCID is required"
        if self.__enroll_project.find_subject(label=record.naccid):
            log.error(
                f"Subject with NACCID {record.naccid} exists in project "
                f"{self.__enroll_project.group}/{self.__enroll_project.label}"
            )

            return False

        subject = self.__enroll_project.add_subject(record.naccid)
        subject.add_enrollment(record)

        return True

    def update_transfer_info(self) -> None:
        """Updates the transfer record status in enrollment project."""
        self.__transfer_record.status = "completed"
        self.__transfer_record.updated_date = datetime.now()
        transfer_info = TransferInfo(transfers={})
        transfer_info.add(self.__transfer_record)
        self.__enroll_project.add_or_update_transfers(transfers=transfer_info)
