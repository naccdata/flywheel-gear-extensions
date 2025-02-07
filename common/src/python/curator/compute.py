from collections import deque
from typing import Any, Dict, Iterator, List, MutableMapping, Optional, overload

from curator.curator import AttributeCondition, ComputeDefinition, ValueDefinition
from dates.form_dates import DEFAULT_DATE_FORMAT, parse_date

# class SymbolTable(MutableMapping):

#     def __init__(self, symbol_dict: Optional[Dict[str, Any]] = None) -> None:
#         self.__table = symbol_dict if symbol_dict else {}

#     def __setitem__(self, key: str, value: Any) -> None:
#         self.__table[key] = value

#     def __getitem__(self, key: str) -> Optional[Any]:
#         value = self.__table
#         key_list = key.split('.')
#         while key_list:
#             sub_key = key_list.pop(0)
#             if not isinstance(value, dict):
#                 raise KeyError

#             value = value.get(sub_key, {})
#         if value:
#             return value

#         return None

#     def __delitem__(self, key: Any) -> None:
#         return

#     def __iter__(self) -> Iterator:
#         return self.__table.__iter__()

#     def __len__(self) -> int:
#         return len(self.__table)


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
                # TODO: raise something ?
                # log.error("expecting dict, got %s", type(obj))
                return None

            table = obj

    def __getitem__(self, key: str) -> Optional[Any]:
        value = self.__table
        key_list = key.split('.')
        while key_list:
            sub_key = key_list.pop(0)
            if not isinstance(value, dict):
                raise KeyError()

            value = value.get(sub_key, {})
        if value:
            return value

        return None

    def __delitem__(self, key: Any) -> None:
        return

    def __iter__(self) -> Iterator:
        return self.__table.__iter__()

    def __len__(self) -> int:
        return len(self.__table)


class TransformDispatch:

    def __init__(self, symbol_table: Optional[SymbolTable] = None) -> None:
        self.__symbol_table: SymbolTable = symbol_table if symbol_table else SymbolTable(
        )

    @overload
    def evaluate(self, *, rule: ComputeDefinition) -> Optional[Any]:
        ...

    @overload
    def evaluate(self, *, value: ValueDefinition) -> Optional[Any]:
        ...

    @overload
    def evaluate(self, *, predicate: AttributeCondition) -> Optional[Any]:
        ...

    def evaluate(
            self,
            *,
            rule: Optional[ComputeDefinition] = None,
            value: Optional[ValueDefinition] = None,
            predicate: Optional[AttributeCondition] = None) -> Optional[Any]:
        if rule:
            return self.execute_builtin(name=rule.compute,
                                        arguments=rule.arguments)

        if value:
            return self.__symbol_table.get(value.attribute)

        if predicate:
            return self.execute_builtin(name=predicate.predicate,
                                        arguments=predicate.arguments)

        return None

    def execute_builtin(self, name: str, arguments: Dict[str, Any]):
        try:
            attribute = getattr(self, name)
        except AttributeError as error:
            raise MissingTransformError(error) from error

        if not callable(attribute):
            raise MissingTransformError(f"{name} is not a transform")

        return attribute(**arguments)

    #
    # Methods for builtin computations
    #
    def apply(self, attribute: str, mapping: Dict[int, str],
              undefined: str) -> Optional[str]:
        """Returns the result of applying the mapping to the value of the
        attribute. Returns undefined value if the attribute value is not a key
        in the mapping.

        Assumes the attribute value is or can be converted to an int.

        Args:
          attribute: the attribute to be mapped
          mapping: the mapping to
          undefined: the return value for mismatched attribute value
        Returns:
          The value in the mapping for the attribute value as key.
          Otherwise, the value of undefined.
        """
        value = self.__symbol_table.get(attribute)
        if not value:
            return None

        result = mapping.get(int(value))
        if not result:
            return undefined

        return result

    def create_object(self, attributes: Dict[str,
                                             str]) -> Optional[Dict[str, Any]]:
        return {
            key: self.__symbol_table.get(value)
            for key, value in attributes.items()
        }

    def first_non_null(self, attributes: List[str]) -> Optional[str]:
        if not attributes:
            return None

        for attribute in attributes:
            value = self.__symbol_table.get(attribute)
            if value:
                return value

        return None

    def if_not_null(self, attribute: str, result: str) -> Optional[str]:
        value = self.__symbol_table.get(attribute)

        return result if value else None

    def select_latest(self, existing_attribute: str,
                      new_attribute: str) -> Optional[Dict[str, Any]]:
        existing_value = self.__symbol_table.get(existing_attribute)
        new_value = self.__symbol_table.get(new_attribute)
        if not existing_value or not new_value:
            return None

        if not isinstance(dict, existing_value) or not isinstance(
                dict, new_value):
            return None

        if 'date' not in existing_value or 'date' not in new_value:
            return None

        existing_date = parse_date(date_string=existing_value.get('date'),
                                   formats=[DEFAULT_DATE_FORMAT])
        new_date = parse_date(date_string=new_value.get('date'),
                              formats=[DEFAULT_DATE_FORMAT])

        if new_date > existing_date:
            return new_value

        return existing_value

    #
    # Builtin predicates
    #
    def is_form(self,
                name: Optional[str] = None,
                version: Optional[str] = None) -> Optional[bool]:
        if not self.__symbol_table.get('forms'):
            return False

        if not name:
            return True

        module = self.__symbol_table.get('forms.json.module')
        assert module, "assume module is set"
        if name.lower() != module.lower():
            return False

        if not version:
            return True

        form_version = self.__symbol_table.get('forms.json.formver')
        assert form_version, "assume formver is set"
        return version.lower() == form_version.lower()


class MissingTransformError(Exception):
    pass
