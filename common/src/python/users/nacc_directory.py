"""Classes for NACC directory user credentials."""

import logging
from datetime import datetime
from typing import Any, Dict, List, NewType, Optional

from flywheel.models.user import User
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from users.authorizations import Authorizations

log = logging.getLogger(__name__)


class PersonName(BaseModel):
    """Type class for a person's name."""

    first_name: str
    last_name: str

    def as_str(self) -> str:
        """Returns this name as a string with first and last names separated by
        a space.

        Returns:
          The first and last name concatenated and separated by a space.
        """
        return f"{self.first_name} {self.last_name}"


EntryDictType = NewType(
    "EntryDictType", Dict[str, str | int | PersonName | Authorizations]
)


class UserEntry(BaseModel):
    """A base directory user entry."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: PersonName
    email: str
    auth_email: Optional[str] = Field(default=None)
    active: bool
    registration_date: Optional[datetime] = None

    @property
    def first_name(self) -> str:
        """The first name for this directory entry."""
        return self.name.first_name

    @property
    def last_name(self) -> str:
        """The last name for this directory entry."""
        return self.name.last_name

    @property
    def full_name(self) -> str:
        """The full name for this directory entry."""
        return self.name.as_str()

    def as_dict(self) -> EntryDictType:
        """Builds a dictionary for this directory entry.

        Returns:
          A dictionary with values of this entry
        """
        return self.model_dump(serialize_as_any=True)  # type: ignore

    @classmethod
    def create(cls, entry: Dict[str, Any]) -> "UserEntry":
        """Creates an object from a dictionary. Expects dictionary to match
        output of `as_dict`

        Args:
          entry: the dictionary for entry
        Returns:
          The dictionary object
        """
        try:
            if entry.get("active"):
                return ActiveUserEntry.create(entry)

            return UserEntry.model_validate(entry)
        except ValidationError as error:
            log.error("Error creating user entry from %s: %s", entry, error)
            raise UserFormatError(f"Error creating user entry: {error}") from error

    @classmethod
    def create_from_record(cls, record: Dict[str, Any]) -> Optional["UserEntry"]:
        """Creates a UserEntry from a data platform authorization report record
        from the NACC Directory in REDCap.

        Creates a UserEntry object if the record is marked as archived.
        Otherwise, creates an ActiveUserEntry.
        Ignores records that have incomplete or unverified authorization emails.

        Args:
          record: a dictionary containing report record for user
        Returns:
          the dictionary entry for the record. None, if record is incomplete
        """

        name = PersonName(first_name=record["firstname"], last_name=record["lastname"])
        email = record["email"].lower()
        auth_email = record.get("fw_email")

        if record["archive_contact"] == "1":
            log.info("Creating inactive user record for %s", email)
            return UserEntry(
                name=name, email=email, auth_email=auth_email, active=False
            )

        if int(record["nacc_data_platform_access_information_complete"]) != 2:
            log.warning("Ignoring user %s: incomplete data platform access", email)
            return None

        authorizations = Authorizations.create_from_record(
            study_id="adrc", activities=record["flywheel_access_activities"]
        )

        org_name = record["contact_company_name"]
        center_id = record["adresearchctr"]
        if not center_id.isdigit():
            center_id = "-1"
            if org_name.lower() == "nacc":
                center_id = "0"

        log.info("Creating active user record for %s", email)
        return ActiveUserEntry(
            org_name=org_name,
            adcid=int(center_id),
            name=name,
            email=email,
            auth_email=auth_email,
            authorizations=authorizations,
            active=True,
        )


class ActiveUserEntry(UserEntry):
    """A user entry from Flywheel access report of the NACC directory."""

    org_name: str
    adcid: int
    authorizations: Authorizations

    def register(self, registry_id: str) -> "RegisteredUserEntry":
        """Adds the registry id to this user entry.

        Args:
          registry_id: the registry ID
        Returns:
          this object with the registry ID added
        """
        return RegisteredUserEntry(
            name=self.name,
            email=self.email,
            auth_email=self.auth_email,
            active=self.active,
            org_name=self.org_name,
            adcid=self.adcid,
            authorizations=self.authorizations,
            registry_id=registry_id,
            registration_date=self.registration_date,
        )

    @classmethod
    def create(cls, entry: Dict[str, Any]) -> "ActiveUserEntry":
        """Creates an object from a dictionary. Expects dictionary to match
        output of `as_dict`

        Args:
          entry: the dictionary for entry
        Returns:
          The dictionary object
        """
        try:
            return ActiveUserEntry.model_validate(entry)
        except ValidationError as error:
            log.error("Error creating user entry from %s: %s", entry, error)
            raise UserFormatError(f"Error creating user entry: {error}") from error


class RegisteredUserEntry(ActiveUserEntry):
    """User directory entry extended with a registry ID."""

    registry_id: str

    @property
    def user_id(self) -> str:
        """The user ID for this directory entry."""
        return self.registry_id

    def as_user(self) -> User:
        """Creates a user object from the directory entry.

        Flywheel constraint (true as of version 17): the user ID and email must be
        the same even if ID is an ePPN in add_user

        Args:
        user_entry: the directory entry for the user
        Returns:
        the User object for flywheel User created from the directory entry
        """
        return User(
            id=self.user_id,
            firstname=self.first_name,
            lastname=self.last_name,
            email=self.user_id,
        )


class UserFormatError(Exception):
    """Exception class for user format errors."""


class UserEntryList(RootModel):
    """Class to support serialization of directory entry list.

    Use model_dump(serialize_as_any=True)
    """

    root: List[UserEntry]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> UserEntry:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, entry: UserEntry) -> None:
        """Appends the user entry to the list."""
        self.root.append(entry)
