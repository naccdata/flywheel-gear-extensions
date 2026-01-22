"""Utility functions."""

from typing import Any, Dict, List, MutableMapping, Optional, Tuple


def parse_string_to_list(
    input_str: Optional[str], to_lower: bool = True, delimiter: str = ","
) -> List[str]:
    """Parses a comma delimited string to a list.

    Args:
        input_str: The input string to parse
        to_lower: Whether or not to set all to lower
        delimiter: The delimiter to split on
    Returns:
        The parsed list
    """
    if not input_str:
        return []

    if to_lower:
        return [x.strip().lower() for x in input_str.split(delimiter)]

    return [x.strip() for x in input_str.split(delimiter)]


def flatten_dict(
    dictionary: MutableMapping, parent_key: str = "", separator: str = "."
) -> Dict[str, Any]:
    """Flattens a dictionary recursively.

    Args:
        dictionary: Dict to flatten
        parent_key: Parent key in recursive nesting
        separator: Separator to use for flattened key, e.g. file.info

    Returns:
        Flattened dict
    """
    items: List[Tuple[str, Any]] = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten_dict(value, new_key, separator=separator).items())
        else:
            items.append((new_key, value))
    return dict(items)


def filter_include_exclude(
    in_list: List[str], include: Optional[str] = None, exclude: Optional[str] = None
) -> List[str]:
    """Filters the given list with the provided include/exclude strings.

    Args:
        in_list: List/set to filter
        include: Comma-delimited string of fields to include
        exclude: Comma-delimited string of fields to exclude

    Returns:
        filtered set
    """
    s_include = set(parse_string_to_list(include))
    s_exclude = set(parse_string_to_list(exclude))

    if (s_include and s_exclude) and s_include.intersection(s_exclude):
        raise ValueError("Include and exclude lists cannot overlap")

    if s_include:
        return [adcid for adcid in in_list if adcid in s_include]
    if s_exclude:
        return [adcid for adcid in in_list if adcid not in s_exclude]

    return in_list
