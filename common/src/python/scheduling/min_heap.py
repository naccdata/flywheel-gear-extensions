from heapq import heappop, heappush
from typing import Generic, TypeVar

from scheduling.comparable import Comparable

T = TypeVar("T", bound=Comparable)


class MinHeap(Generic[T]):
    def __init__(self) -> None:
        self.__minheap: list[T] = []

    def __len__(self):
        return len(self.__minheap)

    def push(self, element: T) -> None:
        heappush(self.__minheap, element)

    def pop(self) -> T | None:
        if len(self.__minheap) > 0:
            return heappop(self.__minheap)

        return None

    def empty(self) -> bool:
        return not self.__minheap
