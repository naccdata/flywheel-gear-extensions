from typing import Iterable, List, TypeVar, Generic

T = TypeVar('T')


class Finder(Generic[T]):

    def find(self, args: str) -> List[T]:
        ...

    def find_first(self, args: str) -> T:
        ...

    def iter(self) -> Iterable[T]:
        ...
