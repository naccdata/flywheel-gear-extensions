"""Functions for extracting event data from QC status log files."""

import logging

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import VisitMetadata
from nacc_common.qc_report import extract_visit_keys

from event_capture.models import SubmitEventData

log = logging.getLogger(__name__)


def extract_event_from_log(log_file: FileEntry) -> SubmitEventData | None:
    """Extract event data from a QC status log file.

    Tries two methods to extract visit metadata:
    1. From file.info.visit (newer files created by identifier_lookup)
    2. From filename parsing (older files without metadata)

    Args:
        log_file: The QC status log file to process

    Returns:
        SubmitEventData object if extraction successful, None otherwise
    """
    # Try to get visit metadata from file custom info first (newer files)
    visit_metadata = VisitMetadata.create(log_file)

    # Fall back to parsing filename if metadata not found (older files)
    if not visit_metadata:
        visit_metadata = _extract_from_filename(log_file.name)

    if not visit_metadata:
        log.warning(f"Could not extract visit metadata from {log_file.name}")
        return None

    # Extract submission timestamp from file creation time
    submission_timestamp = log_file.created

    # Create and return SubmitEventData object
    return SubmitEventData(
        visit_metadata=visit_metadata,
        submission_timestamp=submission_timestamp,
    )


def _extract_from_filename(filename: str) -> VisitMetadata | None:
    """Extract visit metadata from QC status log filename.

    Uses the standard QC filename pattern from nacc_common.qc_report.
    Parses filenames matching pattern: ptid_date_module_qc-status.log
    Example: 110001_2024-01-15_UDS_qc-status.log

    Args:
        filename: The QC status log filename

    Returns:
        VisitMetadata if filename matches pattern, None otherwise
    """
    # Create a mock file object with just the name to use extract_visit_keys
    mock_file = type("obj", (object,), {"name": filename})()

    try:
        visit_keys = extract_visit_keys(mock_file)
        return VisitMetadata(
            ptid=visit_keys.ptid,
            date=visit_keys.date,
            module=visit_keys.module,
            visitnum=None,  # Not available in filename
            packet=None,  # Not available in filename
        )
    except (TypeError, Exception) as error:
        log.debug(f"Failed to extract visit keys from filename {filename}: {error}")
        return None
