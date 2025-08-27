"""Defines wrapper for subject with methods for tracking enrollment."""

import logging
from datetime import datetime
from typing import Optional

from dates.form_dates import DEFAULT_DATE_FORMAT
from flywheel.models.session import Session
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.model import CenterFields, GUIDField, NACCIDField
from keys.keys import DefaultValues
from pydantic import BaseModel, ValidationError

from enrollment.enrollment_transfer import (
    Demographics,
    EnrollmentError,
    EnrollmentRecord,
    EnrollmentStatus,
)

log = logging.getLogger(__name__)


class IdentifierInfoRecord(CenterFields, GUIDField, NACCIDField):
    """Info object for enrollment identifiers object."""

    update_date: datetime
    status: EnrollmentStatus = "active"
    legacy: Optional[bool] = False


class EnrollmentInfo(BaseModel):
    """Wrapper for identifier record."""

    enrollment: Optional[IdentifierInfoRecord]


class DemographicsInfo(BaseModel):
    """Wrapper for demographics record stored as info."""

    demographics: Optional[Demographics]


class EnrollmentSubject(SubjectAdaptor):
    """Wrapper for subject to track enrollment information."""

    @classmethod
    def create_from(cls, subject: SubjectAdaptor) -> "EnrollmentSubject":
        """Converts a SubjectAdaptor to an EnrollmentSubject.

        Args:
          subject: the subject adaptor
        Returns:
          the enrollment subject
        """
        # pylint: disable=protected-access
        return EnrollmentSubject(subject=subject.subject)

    def get_enrollment_info(self) -> Optional[IdentifierInfoRecord]:
        """Returns the enrollment info object for this subject.

        Creates a new object if none exists.

        Return:
          enrollment info object
        """
        info = self.info
        if not info:
            return None
        if "enrollment" not in info:
            return None

        try:
            enrollment_info = EnrollmentInfo.model_validate(info)
            return enrollment_info.enrollment
        except ValidationError as error:
            raise EnrollmentError(
                f"Info for {self.label}does not match expected format"
            ) from error

    def add_enrollment(self, record: EnrollmentRecord) -> None:
        """Adds enrollment information to the subject.

        Args:
          record: the enrollment record
        """
        self.upload_enrollment(record)
        self.update_enrollment_info(record)

    def update_enrollment(self, record: EnrollmentRecord) -> None:
        """Updates the latest enrollment session and enrollment metadata for
        this subject.

        Args:
          record: the enrollment info to be updated

        Raises:
            EnrollmentError: if error occurs while updating info
        """

        # find the latest enrollment session for the subject
        enroll_sessions = self.sessions.find(
            f"label=~{DefaultValues.ENRL_SESSION_LBL_PRFX}",
            sort="created:desc",  # type: ignore
        )

        if enroll_sessions:
            if len(enroll_sessions) > 1:
                log.warning(
                    f"Multiple enrollment sessions found for subject {self.label}"
                )

            enroll_session: Session = enroll_sessions[0]
            session_label = enroll_session.label
            date_str = enroll_session.label[len(DefaultValues.ENRL_SESSION_LBL_PRFX) :]
            record.start_date = datetime.strptime(date_str, DEFAULT_DATE_FORMAT)
        else:
            formdate = record.start_date.strftime(DEFAULT_DATE_FORMAT)
            session_label = f"{DefaultValues.ENRL_SESSION_LBL_PRFX}{formdate}"

        self.upload_acquisition_file(
            session_label=session_label,
            acquisition_label=DefaultValues.ENROLLMENT_MODULE,
            filename=self.get_acquisition_file_name(
                session=session_label, acquisition=DefaultValues.ENROLLMENT_MODULE
            ),
            contents=record.model_dump_json(exclude_none=True),
            content_type="application/json",
            skip_duplicates=False,
        )

        self.update_enrollment_info(record, update_timestamp=datetime.now())

    def update_enrollment_info(
        self, record: EnrollmentRecord, update_timestamp: Optional[datetime] = None
    ) -> None:
        """Update the enrollment info of this subject.

        Args:
          enrollment_info: the enrollment info
          update_timestamp (optional): update timestamp
        """
        assert record.naccid, "record must have NACCID"
        identifiers = IdentifierInfoRecord(
            adcid=record.center_identifier.adcid,
            ptid=record.center_identifier.ptid,
            naccid=record.naccid,
            guid=record.guid,
            update_date=update_timestamp if update_timestamp else record.start_date,
            status=record.status,
            legacy=record.legacy,
        )
        self.update(EnrollmentInfo(enrollment=identifiers).model_dump())

    def upload_enrollment(self, record: EnrollmentRecord) -> None:
        """Uploads a file for the enrollment record to this subject.

        The record is saved as a JSON file under this subject.

        Args:
          record: the enrollment record
        """
        formdate = record.start_date.strftime(DEFAULT_DATE_FORMAT)
        session_label = f"{DefaultValues.ENRL_SESSION_LBL_PRFX}{formdate}"
        self.upload_acquisition_file(
            session_label=session_label,
            acquisition_label=DefaultValues.ENROLLMENT_MODULE,
            filename=self.get_acquisition_file_name(
                session=session_label, acquisition=DefaultValues.ENROLLMENT_MODULE
            ),
            contents=record.model_dump_json(exclude_none=True),
            content_type="application/json",
            skip_duplicates=False,
        )

    def get_demographics_info(self) -> Optional[Demographics]:
        """Returns the demographics info object for this subject.

        Return:
          demographics object if exists. None otherwise
        """
        info = self.info
        if not info:
            return None
        if "demographics" not in info:
            return None

        try:
            demographics_info = DemographicsInfo.model_validate(info)
            return demographics_info.demographics
        except ValidationError as error:
            raise EnrollmentError(
                f"info for {self.label}does not match expected format"
            ) from error

    def update_demographics_info(self, demographics: Demographics) -> None:
        """Updates the demographics info object for this subject.

        Args:
          demographics: the demographics object
        """
        self.update(DemographicsInfo(demographics=demographics).model_dump())
