"""Repository for Identifiers.

Inspired by
https://github.com/cosmicpython/code/tree/chapter_02_repository_exercise
"""

import abc
import builtins
import logging
from abc import abstractmethod
from datetime import date
from typing import overload

from identifiers.model import (
    CenterIdentifiers,
    EnrollmentDurationResponse,
    GUIDField,
    IdentifierList,
    IdentifierObject,
    NACCIDField,
    OptionalNACCADCField,
)

log = logging.getLogger(__name__)


class IdentifierQueryObject(CenterIdentifiers, GUIDField):
    """Query model creating objects."""


class IdentifierUpdateObject(
    CenterIdentifiers, GUIDField, OptionalNACCADCField, NACCIDField
):
    """Request model for identifier updates.

    Has NACCID as string. NACCADC is optional
    """

    active: bool

    @classmethod
    def create_from_identifier(
        cls, identifier: IdentifierObject, active: bool
    ) -> "IdentifierUpdateObject":
        return IdentifierUpdateObject(
            naccid=identifier.naccid,
            adcid=identifier.adcid,
            ptid=identifier.ptid,
            guid=identifier.guid,
            naccadc=identifier.naccadc,
            active=active,
        )


class DateQueryObject(CenterIdentifiers):
    """Request model for checking whether a visitdate is within the valid
    duration for the specified center."""

    visitdate: date


class IdentifierRepository(abc.ABC):
    """Abstract class for identifier repositories."""

    @abstractmethod
    def create(self, adcid: int, ptid: str, guid: str | None) -> IdentifierObject:
        """Creates an Identifier in the repository.

        Args:
          adcid: the center id
          ptid: the center participant ID
          guid: the NIA GUID
        """

    @abstractmethod
    def create_list(self, identifiers: list[IdentifierQueryObject]) -> IdentifierList:
        """Adds a list of identifiers to the repository.

        Args:
          identifiers: the list of Identifiers
        """

    @abstractmethod
    @overload
    def get(self, *, naccid: str) -> IdentifierObject | None: ...

    @abstractmethod
    @overload
    def get(self, *, guid: str) -> IdentifierObject | None: ...

    @abstractmethod
    @overload
    def get(self, *, adcid: int, ptid: str) -> IdentifierObject | None: ...

    @abstractmethod
    def get(
        self,
        *,
        naccid: str | None = None,
        adcid: int | None = None,
        ptid: str | None = None,
        guid: str | None = None,
    ) -> IdentifierObject | None:
        """Returns Identifier object for the IDs given.

        Note: some valid arguments can be falsey.
        These are explicitly checked that they are not None.

        Args:
          naccid: the NACCID
          adcid: the center ID
          ptid: the participant ID assigned by the center
          guid: the NIA GUID
        Returns:
          the identifier for the naccid or the adcid-ptid pair
        Raises:
          NoMatchingIdentifier: if no Identifier record was found
          TypeError: if the arguments are nonsensical
        """

    @abstractmethod
    @overload
    def list(self, *, naccid: str) -> list[IdentifierObject]: ...

    @abstractmethod
    @overload
    def list(self, *, adcid: int) -> builtins.list[IdentifierObject]: ...

    @abstractmethod
    @overload
    def list(self) -> builtins.list[IdentifierObject]: ...

    @abstractmethod
    def list(
        self, *, adcid: int | None = None, naccid: str | None = None
    ) -> builtins.list[IdentifierObject]:
        """Returns the list of all identifiers in the repository.

        If an ADCID is given filters identifiers by the center.
        If an NACCID is given returns identifiers for that NACCID.

        Args:
          adcid: the ADCID used for filtering
          naccid: the NACCID used for filtering

        Returns:
          List of all identifiers in the repository or ones matching with filters
        """

    @abstractmethod
    def add_or_update(self, identifier: IdentifierUpdateObject) -> bool:
        """Adds/updates the Identifier record in the repository.

        Args:
          identifier: Identifier record to add/update

        Returns:
          True if add/update successful, else False
        """

    @abstractmethod
    def check_enrollment_period(
        self, date_query: DateQueryObject
    ) -> EnrollmentDurationResponse | None:
        """Checks whether there is a valid identifier duration record in the
        repository matching with the visit date in query object.

        Args:
          date_query: visitdate query to validate

        Returns:
          EnrollmentDurationResponse (optional) if match found, else None
        """


class IdentifierRepositoryError(Exception):
    """Exception for case when identifier is not matched."""
