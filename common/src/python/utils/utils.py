"""Utility functions."""

import json
import logging
from typing import Any, Dict, List, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException

log = logging.getLogger(__name__)


def is_duplicate_record(record1: str,
                        record2: str,
                        content_type: Optional[str] = None) -> bool:
    """Check whether the two records are identical.

    Args:
        record1: First record
        record2: Second record

    Returns:
        True if a duplicate detected, else false
    """

    if not content_type or content_type != 'application/json':
        return (record1 == record2)

    try:
        dict1 = sorted(json.loads(record1).items())
        dict2 = sorted(json.loads(record2).items())
        return (dict1 == dict2)
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
    """Parses a comma deliminated string to a list.

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
