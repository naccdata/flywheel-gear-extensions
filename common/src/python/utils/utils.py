"""Utility functions."""
import logging
from typing import Any, Dict, List, MutableMapping, Optional, Tuple

from configs.ingest_configs import FormProjectConfigs

log = logging.getLogger(__name__)


def parse_string_to_list(input_str: Optional[str],
                         to_lower: bool = True,
                         delimiter: str = ',') -> List[str]:
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


def load_form_ingest_configurations(
        config_file_path: str) -> FormProjectConfigs:
    """Load the form module configs from the configs file.

    Args:
      config_file_path: the form module configs file path

    Returns:
      FormProjectConfigs

    Raises:
      ValidationError if failed to load the configs file
    """

    with open(config_file_path, mode='r',
              encoding='utf-8-sig') as configs_file:
        return FormProjectConfigs.model_validate_json(configs_file.read())


def flatten_dict(dictionary: MutableMapping,
                 parent_key: str = '',
                 separator: str = '.') -> Dict[str, Any]:
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
            items.extend(
                flatten_dict(value, new_key, separator=separator).items())
        else:
            items.append((new_key, value))
    return dict(items)
