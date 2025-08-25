"""Models to represent information in the Participant enrollment/transfer
form."""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from identifiers.identifiers_repository import (
    IdentifierQueryObject,
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import (
    GUID_PATTERN,
    NACCID_PATTERN,
    PTID_PATTERN,
    CenterIdentifiers,
    GUIDField,
    OptionalNACCIDField,
)
from inputs.csv_reader import RowValidator
from keys.keys import FieldNames, SysErrorCodes
from outputs.error_models import VisitKeys
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    existing_participant_error,
    identifier_error,
    preprocessing_error,
)
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

TransferStatus = Literal["pending", "approved", "rejected"]


class GenderIdentity(BaseModel):
    """Model for Gender Identity demographic data."""

    man: Optional[Literal[1]]
    woman: Optional[Literal[1]]
    transgender_man: Optional[Literal[1]]
    transgender_woman: Optional[Literal[1]]
    nonbinary: Optional[Literal[1]]
    two_spirit: Optional[Literal[1]]
    other: Optional[Literal[1]]
    other_term: Optional[Literal[1]]
    dont_know: Optional[Literal[1]]
    no_answer: Optional[Literal[1]]


class Demographics(BaseModel):
    """Model for demographic data."""

    years_education: int | Literal[99] = Field(ge=0, le=36)
    birth_date: datetime
    gender_identity: GenderIdentity

    @classmethod
    def create_from(cls, row: Dict[str, Any]) -> "Demographics":
        """Constructs a Demographics object from row of enrollment/transfer
        form.

        Assumes form is enrollment form.

        Args:
          row: the dictionary for the row of form.
        Returns:
          Demographics object built from row
        """
        return Demographics(
            years_education=row["enrleduc"],
            birth_date=datetime(int(row["enrlbirthmo"]), int(row["enrlbirthyr"]), 1),
            gender_identity=GenderIdentity(
                man=row["enrlgenman"] if row["enrlgenman"] else None,
                woman=row["enrlgenwoman"] if row["enrlgenwoman"] else None,
                transgender_man=row["enrlgentrman"] if row["enrlgentrman"] else None,
                transgender_woman=row["enrlgentrwoman"]
                if row["enrlgentrwoman"]
                else None,
                nonbinary=row["enrlgennonbi"] if row["enrlgennonbi"] else None,
                two_spirit=row["enrlgentwospir"] if row["enrlgentwospir"] else None,
                other=row["enrlgenoth"] if row["enrlgenoth"] else None,
                other_term=row["enrlgenothx"] if row["enrlgenothx"] else None,
                dont_know=row["enrlgendkn"] if row["enrlgendkn"] else None,
                no_answer=row["enrlgennoans"] if row["enrlgennoans"] else None,
            ),
        )


class TransferRecord(BaseModel):
    """Model representing transfer between centers."""

    status: TransferStatus
    request_date: datetime
    center_identifiers: CenterIdentifiers
    updated_date: datetime
    submitter: str  # FW user who uploaded the transfer form
    initials: Optional[str] = None
    previous_identifiers: Optional[CenterIdentifiers] = None
    naccid: Optional[str] = Field(None, max_length=10, pattern=NACCID_PATTERN)
    guid: Optional[str] = Field(None, max_length=20, pattern=GUID_PATTERN)
    demographics: Optional[Demographics] = None


class EnrollmentRecord(GUIDField, OptionalNACCIDField):
    """Model representing enrollment of participant."""

    center_identifier: CenterIdentifiers
    start_date: datetime
    end_date: Optional[datetime] = None
    transfer_from: Optional[TransferRecord] = None
    transfer_to: Optional[TransferRecord] = None
    legacy: Optional[bool] = False

    def query_object(self) -> IdentifierQueryObject:
        """Creates an object for creating identifiers in the repository.

        Returns:
          the identifier query object to use in batch identifier creation
        """
        return IdentifierQueryObject(
            adcid=self.center_identifier.adcid,
            ptid=self.center_identifier.ptid,
            guid=self.guid,
        )


def has_value(row: Dict[str, Any], variable: str, value: int) -> bool:
    """Implements a check that the variable has the value in the row.

    Args:
      row: dictionary for a data row
      variable: the variable name
      value: the expected value
    Returns:
      True if the variable has the value. False, otherwise.
    """
    return int(row[variable]) == value


def is_new_enrollment(row: Dict[str, Any]) -> bool:
    """Checks if row is a new enrollment.

    Args:
      row: the dictionary for the row.
    Returns:
      True if the row represents a new enrollment. False, otherwise.
    """
    return has_value(row, FieldNames.ENRLTYPE, 1)


def previously_enrolled(row: Dict[str, Any]) -> bool:
    """Checks if row is has previous enrollment set.

    Args:
      row: the dictionary for the row.
    Returns:
      True if the row represents a previous enrollment. False, otherwise.
    """
    return has_value(row, FieldNames.PREVENRL, 1)


def guid_available(row: Dict[str, Any]) -> bool:
    """Checks if row has available GUID.

    Args:
      row: the dictionary for the row
    Returns:
      True if the row indicates the GUID is available
    """
    return has_value(row, FieldNames.GUIDAVAIL, 1)


def has_known_naccid(row: Dict[str, Any]) -> bool:
    """Checks if row has a known NACCID.

    Args:
      row: the dictionary for the row.
    Returns:
      True if the row represents a known NACCID. False, otherwise.
    """
    return has_value(row, FieldNames.NACCIDKWN, 1)


# pylint: disable=(too-few-public-methods)
class NewPTIDRowValidator(RowValidator):
    """Row validator to check that the PTID in the rows does not have a
    NACCID."""

    def __init__(self, repo: IdentifierRepository, error_writer: ErrorWriter) -> None:
        self.__identifiers = repo
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that ADCID, PTID does not already correspond to a NACCID.

        Args:
          row: the dictionary for the row

        Returns:
          True if no existing NACCID is found for the ADCID, PTID, False otherwise
        """
        ptid = row["ptid"]
        adcid = row["adcid"]

        try:
            identifier = self.__identifiers.get(adcid=adcid, ptid=ptid)
        except (IdentifierRepositoryError, TypeError) as error:
            self.__error_writer.write(
                identifier_error(
                    field=FieldNames.PTID,
                    value=ptid,
                    line=line_number,
                    message=(
                        "Error in looking up Identifier for "
                        f"ADCID {adcid}, PTID {ptid}: {error}"
                    ),
                )
            )
            return False

        if not identifier:
            return True

        log.info("Found participant for (%s,%s)", adcid, ptid)
        self.__error_writer.write(
            existing_participant_error(
                field=FieldNames.PTID, line=line_number, value=ptid
            )
        )
        return False


# pylint: disable=(too-few-public-methods)
class NewGUIDRowValidator(RowValidator):
    """Row Validator to check whether a GUID corresponds to an existing
    NACCID."""

    def __init__(self, repo: IdentifierRepository, error_writer: ErrorWriter) -> None:
        self.__identifiers = repo
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that the GUID does not already correspond to a NACCID.

        Args:
          row: the dictionary for the row
        Returns:
          True if no existing NACCID is found for the GUID, False otherwise
        """
        if not guid_available(row):
            return True

        guid = row["guid"]

        try:
            identifier = self.__identifiers.get(guid=guid)
        except (IdentifierRepositoryError, TypeError) as error:
            self.__error_writer.write(
                identifier_error(
                    field=FieldNames.GUID,
                    value=guid,
                    line=line_number,
                    message=f"Error in looking up Identifier for GUID {guid}: {error}",
                )
            )
            return False

        if not identifier:
            return True

        log.info("Found participant for GUID %s", guid)
        self.__error_writer.write(
            existing_participant_error(
                field=FieldNames.GUID,
                line=line_number,
                value=guid,
                message=f"Participant exists for GUID {guid}",
            )
        )
        return False


# pylint: disable=(too-few-public-methods)
# class NoDemographicMatchRowValidator(RowValidator):
#     """Row Validator to check whether the demographics match any existing
#     participants."""

#     def __init__(self, batch: IdentifierBatch,
#                  error_writer: ErrorWriter) -> None:
#         self.__identifiers = batch
#         self.__error_writer = error_writer

#     def check(self, row: Dict[str, Any], line_number: int) -> bool:
#         """Checks that row demographics do not match an existing participant.

#         Args:
#           row: the dictionary for the row
#         Returns:
#           True if no existing participant matches, False otherwise
#         """
#         return True


# pylint: disable=(too-few-public-methods)
class CenterValidator(RowValidator):
    """Row validator to check whether the row has the correct ADCID and the
    PTID matches expected format."""

    def __init__(
        self, center_id: int, date_field: str, error_writer: ErrorWriter
    ) -> None:
        self.__center_id = center_id
        self.__date_field = date_field
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that the row has the expected ADCID and the PTID matches
        expected format.

        Args:
          row: the dictionary for the row
          line_number: the line number of the row

        Returns:
          True if the ADCID matches and PTID in expected format, False otherwise.
        """

        valid = True
        if str(row.get(FieldNames.ADCID)) != str(self.__center_id):
            log.error("Center ID for project must match form ADCID")
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.ADCID,
                    value=row[FieldNames.ADCID],
                    line=line_number,
                    error_code=SysErrorCodes.ADCID_MISMATCH,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )
            valid = False

        ptid = row.get(FieldNames.PTID, "")
        if not re.fullmatch(PTID_PATTERN, ptid):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PTID,
                    value=ptid,
                    line=line_number,
                    error_code=SysErrorCodes.INVALID_PTID,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )
            valid = False

        return valid


class EnrollmentError(Exception):
    """Error class for enrollment."""
