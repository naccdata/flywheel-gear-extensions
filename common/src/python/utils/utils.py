"""Utility functions."""
import copy
import json
import logging
from typing import Any, Dict, List, Optional

from configs.ingest_configs import FormProjectConfigs
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException

log = logging.getLogger(__name__)


def is_duplicate_dict(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> bool:
    """Check whether the two python dicts are identical.

    Args:
        dict1: First dictionary
        dict2: Second dictionary

    Returns:
        True if a duplicate detected, else false
    """

    sorted_dict1 = sorted(dict1.items())
    sorted_dict2 = sorted(dict2.items())
    return (sorted_dict1 == sorted_dict2)


def is_duplicate_record(record1: str,
                        record2: str,
                        content_type: Optional[str] = None) -> bool:
    """Check whether the two records are identical.

    Args:
        record1: First record
        record2: Second record
        content_type (optional): content type
    Returns:
        True if a duplicate detected, else false
    """

    if not content_type or content_type != 'application/json':
        return (record1 == record2)

    try:
        return is_duplicate_dict(json.loads(record1), json.loads(record2))
    except json.JSONDecodeError as error:
        log.warning('Error in converting records to JSON format - %s', error)
        return False

    # TODO: Handle other content types


def update_file_info_metadata(file: FileEntry,
                              input_record: Dict[str, Any],
                              modality: str = 'Form') -> bool:
    """Set file modality and info.forms.json metadata.

    Args:
        file: Flywheel file object
        input_record: input visit data
        modality: file modality (defaults to Form)

    Returns:
        True if metadata update is successful
    """

    # remove empty fields
    non_empty_fields = {k: v for k, v in input_record.items() if v is not None}
    info = {"forms": {"json": non_empty_fields}}

    try:
        file.update(modality=modality)
        file.update_info(info)
    except ApiException as error:
        log.error('Error in setting file %s metadata - %s', file.name, error)
        return False

    return True


def parse_string_to_list(input_str: str,
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
        input_str = ''

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

    with open(config_file_path, mode='r', encoding='utf-8') as configs_file:
        return FormProjectConfigs.model_validate_json(configs_file.read())


def updated_nested_dict(d1: Dict[Any, Any], d2: Dict[Any, Any]) -> Dict[Any, Any]:
    """Deep update d1 with d2 - d2 will replace d1 values EXCEPT
    for lists, which will be appended to the d1 list. Assumes the two
    dicts are compatible, e.g. lists are in the same spots"""

    # if not isinstance(d2, dict):
    #     return d1

    for k, v in d2.items():
        if k in d1:
            if isinstance(v, list):
                if type(v) != type(d1[k]):
                    raise ValueError(f"Cannot update {d1[k]} with {v}")
                d1[k].extend(v)
            elif isinstance(v, dict):
                if type(v) != type(d1[k]):
                    raise ValueError(f"Cannot update {d1[k]} with {v}")
                d1[k] = updated_nested_dict(d1[k], v)
            else:
                d1[k] = v
        else:
            # deep copy in case this is a list/dict.
            d1[k] = copy.deepcopy(v)

    return d1
