from random import randint
from typing import Any

from scheduling.min_heap import MinHeap


class Element:

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Element):
            return False
        return self.value == other.value

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Element):
            return False

        return self.value < other.value


class TestPriorityQueue:

    def test_empty(self):
        queue = MinHeap[Element]()

        assert queue.empty()
        assert queue.pop() is None

    def test_non_empty(self):
        queue = MinHeap[Element]()
        for i in range(10):
            queue.push(Element(randint(i, 1000)))
        assert not queue.empty()
        assert len(queue) == 10
        e1 = queue.pop()
        assert e1
        e2 = queue.pop()
        assert e2
        assert e1 < e2
