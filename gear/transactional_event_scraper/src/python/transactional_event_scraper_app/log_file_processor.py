"""Functions for extracting event data from QC status log files."""

import logging

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import FileQCModel, VisitMetadata
from nacc_common.qc_report import extract_visit_keys

from transactional_event_scraper_app.models import EventData

log = logging.getLogger(__name__)


def extract_event_from_log(log_file: FileEntry) -> EventData | None:
    """Extract event data from a QC status log file.

    Tries two methods to extract visit metadata:
    1. From file.info.visit (newer files created by identifier_lookup)
    2. From filename parsing (older files without metadata)

    Args:
        log_file: The QC status log file to process

    Returns:
        EventData object if extraction successful, None otherwise
    """
    # Try to get visit metadata from file custom info first (newer files)
    visit_metadata = VisitMetadata.create(log_file)

    # Fall back to parsing filename if metadata not found (older files)
    if not visit_metadata:
        visit_metadata = _extract_from_filename(log_file.name)

    if not visit_metadata:
        log.warning(f"Could not extract visit metadata from {log_file.name}")
        return None

    # Determine QC status from file metadata
    qc_model = FileQCModel.create(log_file)
    qc_status = qc_model.get_file_status()

    # Extract timestamps from file attributes
    submission_timestamp = log_file.created
    qc_completion_timestamp = log_file.modified if qc_status == "PASS" else None

    # Create and return EventData object
    return EventData(
        visit_metadata=visit_metadata,
        qc_status=qc_status,
        submission_timestamp=submission_timestamp,
        qc_completion_timestamp=qc_completion_timestamp,
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
