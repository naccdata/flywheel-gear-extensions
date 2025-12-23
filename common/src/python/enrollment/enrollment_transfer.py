"""Models to represent information in the Participant enrollment/transfer
form."""

import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from identifiers.identifiers_repository import (
    IdentifierQueryObject,
    IdentifierRepository,
    IdentifierRepositoryError,
    IdentifierUpdateObject,
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
from nacc_common.field_names import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    existing_participant_error,
    identifier_error,
)
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

TransferStatus = Literal["pending", "approved", "rejected", "completed", "partial"]
EnrollmentStatus = Literal["active", "transferred"]


def empty_str_to_none(value: Any) -> Optional[Any]:
    if isinstance(value, str) and value.strip() == "":
        return None

    return value


class GenderIdentity(BaseModel):
    """Model for Gender Identity demographic data."""

    @field_validator(
        "man",
        "woman",
        "transgender_man",
        "transgender_woman",
        "nonbinary",
        "two_spirit",
        "other",
        "other_term",
        "dont_know",
        "no_answer",
        mode="before",
    )
    def convert_to_none(cls, value: Any) -> Optional[int]:
        return empty_str_to_none(value)

    man: Optional[int] = None
    woman: Optional[int] = None
    transgender_man: Optional[int] = None
    transgender_woman: Optional[int] = None
    nonbinary: Optional[int] = None
    two_spirit: Optional[int] = None
    other: Optional[int] = None
    other_term: Optional[int] = None
    dont_know: Optional[int] = None
    no_answer: Optional[int] = None


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
            birth_date=datetime(int(row["enrlbirthyr"]), int(row["enrlbirthmo"]), 1),
            gender_identity=GenderIdentity(
                man=row.get("enrlgenman"),
                woman=row.get("enrlgenwoman"),
                transgender_man=row.get("enrlgentrman"),
                transgender_woman=row.get("enrlgentrwoman"),
                nonbinary=row.get("enrlgennonbi"),
                two_spirit=row.get("enrlgentwospir"),
                other=row.get("enrlgenoth"),
                other_term=row.get("enrlgenothx"),
                dont_know=row.get("enrlgendkn"),
                no_answer=row.get("enrlgennoans"),
            ),
        )


class TransferRecord(BaseModel):
    """Model representing transfer between centers."""

    @field_validator("naccid", "guid", "initials", "previous_ptid", mode="before")
    def convert_to_none(cls, value: Any) -> Optional[str]:
        return empty_str_to_none(value)

    status: TransferStatus
    request_date: datetime
    center_identifiers: CenterIdentifiers
    updated_date: datetime
    submitter: str  # FW user who uploaded the transfer form
    initials: Optional[str] = None
    previous_adcid: int = Field(ge=0)
    previous_ptid: Optional[str] = Field(None, max_length=10, pattern=PTID_PATTERN)
    naccid: Optional[str] = Field(None, max_length=10, pattern=NACCID_PATTERN)
    guid: Optional[str] = Field(None, max_length=20, pattern=GUID_PATTERN)
    demographics: Optional[Demographics] = None

    def get_identifier_update_object(self, active: bool) -> IdentifierUpdateObject:
        """Creates an object for adding/modifying a record in the repository.

        Returns:
          the identifier update object to add/modify record with known NACCID
        """
        assert self.naccid, "NACCID is required for identifier update"

        return IdentifierUpdateObject(
            naccid=self.naccid,
            adcid=self.center_identifiers.adcid,
            ptid=self.center_identifiers.ptid,
            guid=self.guid,
            active=active,
            naccadc=None,
        )


class EnrollmentRecord(GUIDField, OptionalNACCIDField):
    """Model representing enrollment of participant."""

    center_identifier: CenterIdentifiers
    start_date: datetime
    end_date: Optional[datetime] = None
    status: EnrollmentStatus = "active"
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

        if not identifier or not identifier.active:
            return True

        log.info(
            f"Found active participant for GUID {guid} with NACCID {identifier.naccid}"
        )
        self.__error_writer.write(
            existing_participant_error(
                field=FieldNames.GUID,
                line=line_number,
                value=guid,
                message=(
                    f"Active participant exists for GUID {guid} "
                    f"with NACCID {identifier.naccid}"
                ),
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


class EnrollmentError(Exception):
    """Error class for enrollment."""
