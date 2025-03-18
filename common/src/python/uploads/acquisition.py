import json
import logging
from typing import Any, Dict, Optional

from flywheel.file_spec import FileSpec
from flywheel.models.acquisition import Acquisition
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


def upload_to_acquisition(acquisition: Acquisition,
                          filename: str,
                          contents: str,
                          content_type: str,
                          subject_label: str,
                          session_label: str,
                          acquisition_label: str,
                          skip_duplicates: bool = True) -> Optional[FileEntry]:
    if skip_duplicates:
        existing_file = acquisition.get_file(filename)
        if existing_file and is_duplicate_record(
                contents, existing_file.read(), content_type):
            log.warning('Duplicate file %s already exists at %s/%s/%s',
                        filename, subject_label, session_label,
                        acquisition_label)
            return None

    record_file_spec = FileSpec(name=filename,
                                contents=contents,
                                content_type=content_type)

    try:
        acquisition.upload_file(record_file_spec)
        acquisition = acquisition.reload()
        return acquisition.get_file(filename)
    except ApiException as error:
        raise ApiException(
            f'Failed to upload file {filename} to '
            f'{subject_label}/{session_label}/{acquisition_label}: {error}'
        ) from error
