from collections import deque
from typing import Any, Dict, Iterator, MutableMapping, Optional


class SymbolTable(MutableMapping):
    """Implements a dictionary like object for using metadata paths as keys."""

    def __init__(self, symbol_dict: Optional[Dict[str, Any]] = None) -> None:
        self.__table = symbol_dict if symbol_dict else {}

    def __setitem__(self, key: str, value: Any) -> None:
        table = self.__table
        key_list = deque(key.split('.'))
        while key_list:
            sub_key = key_list.popleft()
            obj = table.get(sub_key)
            if not obj:
                if not key_list:
                    table[sub_key] = value
                    return

                table[sub_key] = {}
                table = table[sub_key]
                continue

            if not key_list:
                table[sub_key] = value
                return

            if not isinstance(obj, dict):
                raise KeyError("Key %s maps to atomic value", key)

            table = obj

    def __getitem__(self, key: str) -> Optional[Any]:
        value = self.__table
        key_list = key.split('.')
        while key_list:
            sub_key = key_list.pop(0)
            if not isinstance(value, dict):
                raise KeyError()

            value = value.get(sub_key)

        return value

    def __delitem__(self, key: Any) -> None:
        return

    def __iter__(self) -> Iterator:
        return self.__table.__iter__()

    def __len__(self) -> int:
        return len(self.__table)
