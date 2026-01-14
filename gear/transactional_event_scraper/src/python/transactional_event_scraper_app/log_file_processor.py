"""Functions for extracting event data from QC status log files."""

import logging

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import FileQCModel, VisitMetadata

from transactional_event_scraper_app.models import EventData

log = logging.getLogger(__name__)


def extract_event_from_log(log_file: FileEntry) -> EventData | None:
    """Extract event data from a QC status log file.

    Args:
        log_file: The QC status log file to process

    Returns:
        EventData object if extraction successful, None otherwise
    """
    # Extract visit metadata
    visit_metadata = VisitMetadata.create(log_file)
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
        log_file=log_file,
        visit_metadata=visit_metadata,
        qc_status=qc_status,
        submission_timestamp=submission_timestamp,
        qc_completion_timestamp=qc_completion_timestamp,
    )
