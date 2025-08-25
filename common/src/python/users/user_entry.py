"""Defines models for representing user entries in the directory."""
import logging
from datetime import datetime
from typing import NewType, Optional

from flywheel.models.user import User
from pydantic import BaseModel, ConfigDict, Field, RootModel

from users.authorizations import StudyAuthorizations

log = logging.getLogger(__name__)


class PersonName(BaseModel):
    """Data model for a person's name."""

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
    "EntryDictType", dict[str, str | int | PersonName | StudyAuthorizations]
)


class UserEntry(BaseModel):
    """A base directory user entry."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: PersonName
    email: str
    auth_email: Optional[str] = Field(default=None)
    active: bool
    approved: bool
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


class ActiveUserEntry(UserEntry):
    """A user entry from Flywheel access report of the NACC directory."""

    org_name: str
    adcid: int
    authorizations: list[StudyAuthorizations]

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

    root: list[UserEntry]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> UserEntry:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, entry: UserEntry) -> None:
        """Appends the user entry to the list."""
        self.root.append(entry)
