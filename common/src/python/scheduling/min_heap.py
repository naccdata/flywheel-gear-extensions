from heapq import heappop, heappush
from typing import Generic, List, Optional, TypeVar

from scheduling.comparable import Comparable

T = TypeVar('T', bound=Comparable)


class MinHeap(Generic[T]):

    def __init__(self) -> None:
        self.__minheap: List[T] = []

    def __len__(self):
        return len(self.__minheap)

    def push(self, element: T) -> None:
        heappush(self.__minheap, element)

    def pop(self) -> Optional[T]:
        if len(self.__minheap) > 0:
            return heappop(self.__minheap)

        return None

    def empty(self) -> bool:
        return not self.__minheap
