"""File visit annotator for submission logger."""

import logging
from typing import Any

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import VisitKeys

log = logging.getLogger(__name__)


class FileVisitAnnotator:
    """Annotates QC status log files with visit metadata.

    Each QC status log file corresponds to a specific visit found during
    single-file processing by the submission logger gear.
    """

    def __init__(self, project: ProjectAdaptor):
        """Initialize file visit annotator.

        Args:
            project: Project adaptor for file operations
        """
        self.__project = project

    def annotate_qc_log_file(self, qc_log_filename: str, visit_keys: VisitKeys) -> bool:
        """Add visit metadata to a QC status log file.

        Args:
            qc_log_filename: Name of the QC status log file
            visit_keys: Visit identification information for this specific visit

        Returns:
            True if visit annotation was successful, False otherwise
        """
        if not visit_keys.ptid or not visit_keys.date or not visit_keys.module:
            log.warning(
                f"Insufficient visit data for annotation: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"module={visit_keys.module}"
            )
            return False

        try:
            # Get the QC status log file
            qc_log_file = self.__project.get_file(qc_log_filename)
            if not qc_log_file:
                log.error(f"QC status log file not found: {qc_log_filename}")
                return False

            # Prepare visit metadata for this specific visit
            visit_metadata = self._create_visit_metadata(visit_keys)

            # Update file info with visit metadata
            info_update = {"visit": visit_metadata}
            qc_log_file.update_info(info_update)

            log.info(f"Added visit metadata to QC log: {qc_log_filename}")
            return True

        except Exception as error:
            log.error(
                f"Failed to add visit metadata to QC log {qc_log_filename}: {error}"
            )
            return False

    def _create_visit_metadata(self, visit_keys: VisitKeys) -> dict[str, Any]:
        """Create visit metadata dictionary for a single visit.

        Args:
            visit_keys: Visit identification information

        Returns:
            Visit metadata dictionary
        """
        # Use Pydantic model_dump() to serialize the VisitKeys directly
        return visit_keys.model_dump(exclude_none=True)
