"""Defines wrapper for subject with methods for tracking enrollment."""

from datetime import datetime
from typing import Optional

from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.model import GUID_PATTERN, NACCID_PATTERN
from pydantic import BaseModel, Field, ValidationError

from enrollment.enrollment_transfer import (
    Demographics,
    EnrollmentError,
    EnrollmentRecord,
)


class IdentifierInfoRecord(BaseModel):
    """Info object for enrollment identifiers object."""
    adcid: int = Field(ge=0)
    ptid: str = Field(max_length=10)
    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)
    guid: Optional[str] = Field(max_length=13, pattern=GUID_PATTERN)
    update_date: datetime


class EnrollmentInfo(BaseModel):
    """Wrapper for identifier record."""
    enrollment: Optional[IdentifierInfoRecord]


class DemographicsInfo(BaseModel):
    """Wrapper for demographics record stored as info."""
    demographics: Optional[Demographics]


class EnrollmentSubject(SubjectAdaptor):
    """Wrapper for subject to track enrollment information."""

    @classmethod
    def create_from(cls, subject: SubjectAdaptor) -> 'EnrollmentSubject':
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
        if 'enrollment' not in info:
            return None

        try:
            enrollment_info = EnrollmentInfo.model_validate(info)
            return enrollment_info.enrollment
        except ValidationError as error:
            raise EnrollmentError(f"Info for {self.label}"
                                  "does not match expected format") from error

    def add_enrollment(self, record: EnrollmentRecord) -> None:
        """Adds enrollment information to the subject.

        Args:
          record: the enrollment record
        """
        self.upload_enrollment(record)
        self.update_enrollment_info(record)

    def update_enrollment_info(self, record: EnrollmentRecord) -> None:
        """Update the enrollment info of this subject.

        Args:
          enrollment_info: the enrollment info
        """
        assert record.naccid, "record must have NACCID"
        identifiers = IdentifierInfoRecord(
            adcid=record.center_identifier.adcid,
            ptid=record.center_identifier.ptid,
            naccid=record.naccid,
            guid=record.guid,
            update_date=record.start_date)
        self.update(EnrollmentInfo(enrollment=identifiers).model_dump())

    def upload_enrollment(self, record: EnrollmentRecord) -> None:
        """Uploads a file for the enrollment record to this subject.

        The record is saved as a JSON file
        `enrollment_transfer/enrollment/enrollment.json`
        under this subject.

        Args:
          record: the enrollment record
        """
        self.upload_acquisition_file(
            session_label='enrollment_transfer',
            acquisition_label='enrollment',
            filename='enrollment.json',
            contents=record.model_dump_json(exclude_none=True),
            content_type='application/json',
            skip_duplicates=False)

    def get_demographics_info(self) -> Optional[Demographics]:
        """Returns the demographics info object for this subject.

        Return:
          demographics object if exists. None otherwise
        """
        info = self.info
        if not info:
            return None
        if 'demographics' not in info:
            return None

        try:
            demographics_info = DemographicsInfo.model_validate(info)
            return demographics_info.demographics
        except ValidationError as error:
            raise EnrollmentError(f"info for {self.label}"
                                  "does not match expected format") from error

    def update_demographics_info(self, demographics: Demographics) -> None:
        """Updates the demographics info object for this subject.

        Args:
          demographics: the demographics object
        """
        self.update(DemographicsInfo(demographics=demographics).model_dump())
