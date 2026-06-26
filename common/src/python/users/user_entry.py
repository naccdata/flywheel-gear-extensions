"""Defines models for representing user entries in the directory."""

import logging
from datetime import datetime
from typing import NewType, Optional

from flywheel.models.user import User
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from users.authorizations import Authorizations, StudyAuthorizations
from users.user_registry import RegistryPerson

log = logging.getLogger(__name__)


class PersonName(BaseModel):
    """Data model for a person's name."""

    first_name: str
    last_name: str

    @field_validator("first_name", "last_name", mode="before")
    def strip_names(cls, value: str) -> str:
        """Strip leading and trailing whitespace from names.

        Provides defense-in-depth to ensure names are normalized even if
        they bypass DirectoryAuthorizations validation.

        Args:
            value: the name value to strip

        Returns:
            the name with leading and trailing whitespace removed
        """
        if isinstance(value, str):
            return value.strip()
        return value

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
    """A user entry for a user with general authorizations.

    Can be in a registered or unregistered state based on whether
    registry_person is set.
    """

    model_config = ConfigDict(
        populate_by_name=True, extra="forbid", arbitrary_types_allowed=True
    )

    authorizations: Authorizations
    registry_person: Optional[RegistryPerson] = Field(default=None, exclude=True)
    fw_user: Optional[User] = Field(default=None, exclude=True)

    @property
    def is_registered(self) -> bool:
        """Check if this user entry has been registered.

        Returns:
            True if registry_person is set, False otherwise
        """
        return self.registry_person is not None

    @property
    def registry_id(self) -> Optional[str]:
        """Get the registry ID from the registry person.

        Returns:
            The registry ID if registered, None otherwise
        """
        if not self.registry_person:
            return None
        return self.registry_person.registry_id()

    @property
    def user_id(self) -> Optional[str]:
        """The user ID for this directory entry.

        Returns:
            The registry_id if registered, None otherwise
        """
        return self.registry_id

    def register(self, registry_person: RegistryPerson) -> None:
        """Attaches the registry person to this user entry.

        Mutates this object to add the registry person, marking it as registered.

        Args:
            registry_person: the RegistryPerson object to attach
        """
        self.registry_person = registry_person

    def set_fw_user(self, fw_user: User) -> None:
        """Attaches the Flywheel user to this user entry.

        Mutates this object to add the Flywheel user.

        Args:
            fw_user: the Flywheel User object to attach
        """
        self.fw_user = fw_user

    def as_user(self) -> User:
        """Creates a user object from the directory entry.

        Flywheel constraint (true as of version 17): the user ID and email must be
        the same even if ID is an ePPN in add_user

        Returns:
            The User object for flywheel User created from the directory entry

        Raises:
            ValueError: if the user entry is not registered
        """
        if not self.is_registered:
            raise ValueError(
                f"Cannot create User from unregistered entry: {self.email}"
            )

        registry_id = self.registry_id
        assert registry_id is not None  # for type checker

        return User(
            id=registry_id,
            firstname=self.first_name,
            lastname=self.last_name,
            email=registry_id,
        )


class CenterUserEntry(ActiveUserEntry):
    """A user entry for a user associated with a research center.

    Can be in a registered or unregistered state based on whether
    registry_person is set (inherited from ActiveUserEntry).
    """

    org_name: str
    adcid: int
    study_authorizations: list[StudyAuthorizations]


class UserFormatError(Exception):
    """Exception class for user format errors."""


class UserEntryList(RootModel):
    """Class to support serialization of directory entry list.

    Use model_dump(serialize_as_any=True)
    """

    root: list[CenterUserEntry | ActiveUserEntry | UserEntry]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> UserEntry:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, entry: UserEntry) -> None:
        """Appends the user entry to the list."""
        self.root.append(entry)
