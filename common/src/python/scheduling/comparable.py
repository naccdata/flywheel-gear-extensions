from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class Comparable(Protocol):

    @abstractmethod
    def __lt__(self: SupportsOrdering, other: SupportsOrdering) -> bool:
        pass

    @abstractmethod
    def __eq__(self: Comparable, other: object) -> bool:
        pass


SupportsOrdering = TypeVar("SupportsOrdering", bound=Comparable)
