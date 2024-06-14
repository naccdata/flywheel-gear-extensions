"""Models to represent information in the Participant enrollment/transfer
form."""

import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from identifiers.identifiers_repository import IdentifierRepository
from identifiers.model import CenterIdentifiers
from inputs.csv_reader import RowValidator
from outputs.errors import CSVLocation, ErrorWriter, FileError
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


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
    def create_from(cls, row: Dict[str, Any]) -> 'Demographics':
        """Constructs a Demographics object from row of enrollment/transfer
        form.

        Assumes form is PTENRLv1.

        Args:
          row: the dictionary for the row of form.
        Returns:
          Demographics object built from row
        """
        return Demographics(
            years_education=row['enrleduc'],
            birth_date=datetime(int(row['enrlbirthmo']),
                                int(row['enrlbirthyr']), 1),
            gender_identity=GenderIdentity(
                man=row['enrlgenman'] if row['enrlgenman'] else None,
                woman=row['enrlgenwoman'] if row['enrlgenwoman'] else None,
                transgender_man=row['enrlgentrman']
                if row['enrlgentrman'] else None,
                transgender_woman=row['enrlgentrwoman']
                if row['enrlgentrwoman'] else None,
                nonbinary=row['enrlgennonbi'] if row['enrlgennonbi'] else None,
                two_spirit=row['enrlgentwospir']
                if row['enrlgentwospir'] else None,
                other=row['enrlgenoth'] if row['enrlgenoth'] else None,
                other_term=row['enrlgenothx'] if row['enrlgenothx'] else None,
                dont_know=row['enrlgendkn'] if row['enrlgendkn'] else None,
                no_answer=row['enrlgennoans']
                if row['enrlgennoans'] else None))


class TransferRecord(BaseModel):
    """Model representing transfer between centers."""
    date: datetime
    initials: str
    center_identifiers: CenterIdentifiers
    previous_identifiers: Optional[CenterIdentifiers]
    naccid: Optional[str] = Field(min_length=10, pattern=r"^NACC\d{6}$")


class EnrollmentRecord(BaseModel):
    """Model representing enrollment of participant."""
    center_identifier: CenterIdentifiers
    naccid: Optional[str] = Field(None, min_length=10, pattern=r"^NACC\d{6}$")
    guid: Optional[str] = Field(None, min_length=13)
    start_date: datetime
    end_date: Optional[datetime] = None
    transfer_from: Optional[TransferRecord] = None
    transfer_to: Optional[TransferRecord] = None

    @classmethod
    def create_from(cls, row: Dict[str, Any]) -> 'EnrollmentRecord':
        """Creates an enrollment record from row of enrollment/transfer form.

        Assumes form is PTERNLv1.

        Args:
          row: the dictionary for the row of form data
        Returns:
          EnrollmentRecord for the row.
        """
        guid = row.get('guid', None)
        if not guid:
            guid = None

        return EnrollmentRecord(center_identifier=CenterIdentifiers(
            adcid=row['adcid'], ptid=row['ptid']),
                                guid=guid,
                                naccid=None,
                                start_date=row['frmdate_enrl'])


def has_value(row: Dict[str, Any], variable: str, value: int) -> bool:
    """Implements a check that the variable has the value in the row.

    Args:
      row: dictionary for a data row
      variable: the variable name
      value: the expected valute
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
    return has_value(row, 'enrltype', 1)


def previously_enrolled(row: Dict[str, Any]) -> bool:
    """Checks if row is has previous enrollment set.

    Args:
      row: the dictionary for the row.
    Returns:
      True if the row represents a previous enrollment. False, otherwise.
    """
    return has_value(row, 'prevenrl', 1)


def guid_available(row: Dict[str, Any]) -> bool:
    """Checks if row has available GUID.

    Args:
      row: the dictionary for the row
    Returns:
      True if the row indicates the GUID is available
    """
    return has_value(row, 'guidavail', 1)


def has_known_naccid(row: Dict[str, Any]) -> bool:
    """Checks if row has a known NACCID.

    Args:
      row: the dictionary for the row.
    Returns:
      True if the row represents a known NACCID. False, otherwise.
    """
    return has_value(row, 'naccidknwn', 1)


def existing_participant_error(field: str,
                               value: str,
                               line: int,
                               message: Optional[str] = None) -> FileError:
    """Creates a FileError for unexpected existing participant."""
    error_message = message if message else ('Participant exists for PTID '
                                             f'{value}')
    return FileError(error_type='error',
                     error_code='participant-exists',
                     location=CSVLocation(column_name=field, line=line),
                     message=error_message)


# pylint: disable=(too-few-public-methods)
class NewPTIDRowValidator(RowValidator):
    """Row validator to check that the PTID in the rows does not have a
    NACCID."""

    def __init__(self, repo: IdentifierRepository,
                 error_writer: ErrorWriter) -> None:
        self.__identifiers = repo
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that PTID does not already correspond to a NACCID.

        Args:
          row: the dictionary for the row
        Returns:
          True if no existing NACCID is found for the PTID, False otherwise
        """
        ptid = row['ptid']
        identifier = self.__identifiers.get(adcid=row['adcid'], ptid=ptid)
        if not identifier:
            return True

        log.info('Found participant for (%s,%s)', row['adcid'], row['ptid'])
        self.__error_writer.write(
            existing_participant_error(field='ptid',
                                       line=line_number,
                                       value=ptid))
        return False


# pylint: disable=(too-few-public-methods)
class NewGUIDRowValidator(RowValidator):
    """Row Validator to check whether a GUID corresponds to an existing
    NACCID."""

    def __init__(self, repo: IdentifierRepository,
                 error_writer: ErrorWriter) -> None:
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

        guid = row['guid']
        identifier = self.__identifiers.get(guid=guid)
        if not identifier:
            return True

        log.info('Found participant for GUID %s', row['guid'])
        self.__error_writer.write(
            existing_participant_error(
                field='guid',
                line=line_number,
                value=guid,
                message=f'Participant exists for GUID {guid}'))
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
