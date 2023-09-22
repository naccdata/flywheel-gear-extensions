from typing import Generic, List, TypeVar

T = TypeVar('T')


class Finder(Generic[T]):

    def find(self, args: str) -> List[T]:
        ...
