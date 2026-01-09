"""Mocks identifiers.identifiers_lambda_repository."""

from datetime import datetime
from typing import Dict, List, Optional, overload

from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from identifiers.identifiers_repository import (
    DateQueryObject,
    EnrollmentDurationResponse,
    IdentifierQueryObject,
    IdentifierUpdateObject,
)
from identifiers.model import IdentifierList, IdentifierObject


class MockIdentifiersLambdaRepository(IdentifiersLambdaRepository):
    def __init__(self, identifiers: Dict[str, IdentifierObject]):
        """Mock identifiers repository by manually setting identifiers. For
        testing we just assume all belong to the same ADCID.

        Args:
            identifiers: Mapping of PTID to IdentifierObject
        """
        self.__identifiers = identifiers

    def create(self, adcid: int, ptid: str, guid: Optional[str]) -> IdentifierObject:
        """Creates an Identifier in the repository.

        Args:
          adcid: the ADCID
          ptid: the participant ID
          guid: the NIA GUID
        Returns:
          The created Identifier
        """
        identifier = IdentifierObject(
            naccid="NACC00000",
            adcid=adcid,
            ptid=ptid,
            guid=guid,
            naccadc=999,
            active=True,
            created_on=datetime.now(),
        )

        self.__identifiers[ptid] = identifier
        return identifier

    def create_list(self, identifiers: List[IdentifierQueryObject]) -> IdentifierList:
        """Creates several Identifiers in the repository.

        Args:
          identifiers: list of identifiers requests
        Returns:
           list of Identifier objects
        """
        identifier_list = [
            self.create(identifier.adcid, identifier.ptid, identifier.guid)
            for identifier in identifiers
        ]

        return IdentifierList(root=identifier_list)

    @overload
    def get(self, *, naccid: str) -> IdentifierObject: ...

    # pylint: disable=(arguments-differ)
    @overload
    def get(self, *, guid: str) -> IdentifierObject: ...

    # pylint: disable=(arguments-differ)
    @overload
    def get(self, *, adcid: int, ptid: str) -> IdentifierObject: ...

    def get(
        self,
        naccid: Optional[str] = None,
        adcid: Optional[int] = None,
        ptid: Optional[str] = None,
        guid: Optional[str] = None,
    ) -> Optional[IdentifierObject]:
        """Returns IdentifierObject object for the IDs given.

        Note: some valid arguments can be falsey.
        These are explicitly checked that they are not None.

        Args:
          naccid: the (integer part of the) NACCID
          adcid: the center ID
          ptid: the participant ID assigned by the center
          guid: the NIA GUID
        Returns:
          the IdentifierObject for the nacc_id or the adcid-ptid pair
        """
        for identifier in self.__identifiers.values():
            if naccid is not None and identifier.naccid == naccid:
                return identifier

            if (adcid is not None and ptid) and (
                identifier.adcid == adcid and identifier.ptid == ptid
            ):
                return identifier

            if guid and identifier.guid == guid:
                return identifier

        raise TypeError("Invalid arguments")

    def list(
        self, *, adcid: Optional[int] = None, naccid: Optional[str] = None
    ) -> List[IdentifierObject]:
        """Returns the list of all identifiers in the repository. For testing
        we assume all belong to same ADCID, so just always return all.

        Args:
          adcid: the ADCID used for filtering
          naccid: the NACCID used for filtering

        Returns:
          List of all identifiers in the repository or ones matching with filters
        """
        return list(self.__identifiers.values())

    def add_or_update(self, identifier: IdentifierUpdateObject) -> bool:
        """Adds/updates an identifier record with known NACCID to the database.
        Update the active status of the identifier record if found or add a new
        identifier record for provided (ADCID, PTID, NACCID).

        Args:
          identifier: Identifier record to add/update

        Returns:
          True if add/update successful, else false
        """
        self.__identifiers[identifier.ptid] = IdentifierObject(
            naccid=identifier.naccid,
            adcid=identifier.adcid,
            ptid=identifier.ptid,
            guid=identifier.guid,
            naccadc=identifier.naccadc,
            active=identifier.active,
        )
        return True

    def check_enrollment_period(
        self, date_query: DateQueryObject
    ) -> Optional[EnrollmentDurationResponse]:
        """Not implemented for testing."""
        return None
