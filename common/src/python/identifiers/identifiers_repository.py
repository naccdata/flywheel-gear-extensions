"""Repository for Identifiers.

Inspired by
https://github.com/cosmicpython/code/tree/chapter_02_repository_exercise
"""

import abc
import logging
from abc import abstractmethod
from typing import List, Optional, overload

from identifiers.model import IdentifierObject

log = logging.getLogger(__name__)


class IdentifierRepository(abc.ABC):

    @abstractmethod
    def create(self, adcid: int, ptid: str) -> IdentifierObject:
        """Creates an Identifier in the repository.

        Args:
          identifier: the Identifier object to add
        """

    @abstractmethod
    def create_list(self, identifiers) -> List[IdentifierObject]:
        """Adds a list of identifiers to the repository.

        Args:
          identifiers: the list of Identifiers
        """

    @abstractmethod
    @overload
    def get(self, *, naccid: int) -> IdentifierObject:
        ...

    @abstractmethod
    @overload
    def get(self, *, guid: str) -> IdentifierObject:
        ...

    @abstractmethod
    @overload
    def get(self,
            *,
            adcid: int,
            ptid: str,
            naccid: Optional[int] = None) -> IdentifierObject:
        ...

    @abstractmethod
    def get(self,
            *,
            naccid: Optional[int] = None,
            adcid: Optional[int] = None,
            ptid: Optional[str] = None,
            guid: Optional[str] = None) -> IdentifierObject:
        """Returns Identifier object for the IDs given.

        Note: some valid arguments can be falsey.
        These are explicitly checked that they are not None.

        Args:
          naccid: the (integer part of the) NACCID
          adc_id: the center ID
          ptid: the participant ID assigned by the center
        Returns:
          the identifier for the naccid or the adcid-ptid pair
        Raises:
          NoMatchingIdentifier: if no Identifier record was found
          TypeError: if the arguments are nonsensical
        """

    @abstractmethod
    @overload
    def list(self, adc_id: int) -> List[IdentifierObject]:
        ...

    @abstractmethod
    @overload
    def list(self) -> List[IdentifierObject]:
        ...

    @abstractmethod
    def list(self, adc_id: Optional[int] = None) -> List[IdentifierObject]:
        """Returns the list of all identifiers in the repository.

        If an ADCID is given filters identifiers by the center.

        Args:
          adc_id: the ADCID used for filtering

        Returns:
          List of all identifiers in the repository
        """


class NoMatchingIdentifier(Exception):
    """Exception for case when identifier is not matched."""
