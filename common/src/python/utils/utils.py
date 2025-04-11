"""Utility functions."""
import logging
from typing import Any, Dict, List

from configs.ingest_configs import FormProjectConfigs
from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException

log = logging.getLogger(__name__)


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

    with open(config_file_path, mode='r', encoding='utf-8') as configs_file:
        return FormProjectConfigs.model_validate_json(configs_file.read())
