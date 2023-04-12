"""Classes for NACC directory user credentials."""

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict


class Authorizations(TypedDict):
    """Type class for authorizations."""
    submit: List[str]
    audit_data: bool
    approve_data: bool
    view_reports: bool


class Credentials(TypedDict):
    """Type class for credentials."""
    type: str
    id: str


class PersonName(TypedDict):
    """Type class for a person's name."""
    first_name: str
    last_name: str


class UserDirectoryEntry:
    """A user entry from Flywheel access report of the NACC directory."""

    def __init__(self, *, org_name: str, center_id: int, name: PersonName,
                 email: str, authorizations: Authorizations,
                 credentials: Credentials, submit_time: datetime) -> None:
        self.__org_name = org_name
        self.__center_id = center_id
        self.__name = name
        self.__email = email
        self.__authorizations = authorizations
        self.__credentials = credentials
        self.__submit_time = submit_time

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, UserDirectoryEntry):
            return False

        return (self.__org_name == __value.org_name
                and self.__center_id == __value.center_id
                and self.__name == __value.name
                and self.__email == __value.email
                and self.__authorizations == __value.authorizations
                and self.__credentials == __value.credentials)

    @property
    def org_name(self) -> str:
        """The name of the user's organization."""
        return self.__org_name

    @property
    def center_id(self) -> int:
        """The ID for the user's center."""
        return self.__center_id

    @property
    def name(self) -> PersonName:
        """The user's name."""
        return self.__name

    @property
    def email(self) -> str:
        """The user's organizational email."""
        return self.__email

    @property
    def authorizations(self) -> Authorizations:
        """The users authorizations for data access."""
        return self.__authorizations

    @property
    def credentials(self) -> Credentials:
        """The users CILogon credentials."""
        return self.__credentials

    @property
    def submit_time(self) -> datetime:
        """The submission time for credentials."""
        return self.__submit_time

    def as_dict(self):
        """Builds a dictionary for this directory entry.

        Returns:
          A dictionary with values of this entry
        """
        result = {}
        result['org_name'] = self.__org_name
        result['center_id'] = self.__center_id
        result['name'] = self.__name
        result['email'] = self.__email
        result['authorizations'] = self.__authorizations
        result['credentials'] = self.__credentials
        result['submit_time'] = self.__submit_time
        return result

    @classmethod
    def create(cls, entry: Dict[str, Any]) -> "UserDirectoryEntry":
        """Creates an object from a dictionary. Expects dictionary to match
        output of `as_dict`

        Args:
          entry: the dictionary for entry
        Returns:
          The dictionary object
        """
        return UserDirectoryEntry(org_name=entry['org_name'],
                                  center_id=entry['center_id'],
                                  name=entry['name'],
                                  email=entry['email'],
                                  authorizations=entry['authorizations'],
                                  credentials=entry['credentials'],
                                  submit_time=entry['submit_time'])

    @classmethod
    def create_from_record(
            cls, record: Dict[str, str]) -> Optional['UserDirectoryEntry']:
        """Creates a DirectoryEntry from a Flywheel Access report record from
        the NACC Directory in REDCap.

        Ignores records that are incomplete or unverified

        Args:
          record: a dictionary containing report record for user
        Returns:
          the dictionary entry for the record. None, if record is incomplete
        """
        if int(record["flywheel_access_information_complete"]) != 2:
            return None

        modalities = []
        activities = record["flywheel_access_activities"]
        if 'a' in activities:
            modalities.append('form')
        if 'b' in activities:
            modalities.append('image')

        authorizations: Authorizations = {
            "submit": modalities,
            "audit_data": bool('c' in activities),
            "approve_data": bool('d' in activities),
            "view_reports": bool('e' in activities)
        }

        credentials: Credentials = {
            "type": record['fw_credential_type'],
            "id": record['fw_credential_id']
        }

        name: PersonName = {
            "first_name": record['firstname'],
            "last_name": record['lastname']
        }

        org_name = record['contact_company_name']
        center_id = record['adresearchctr']
        if not center_id.isdigit():
            center_id = '-1'
            if org_name.lower() == 'nacc':
                center_id = '0'

        return UserDirectoryEntry(org_name=org_name,
                                  center_id=int(center_id),
                                  name=name,
                                  email=record['email'],
                                  credentials=credentials,
                                  submit_time=datetime.strptime(
                                      record['fw_cred_sub_time'],
                                      "%Y-%m-%d %H:%M"),
                                  authorizations=authorizations)
