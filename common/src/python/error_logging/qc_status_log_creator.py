"""QC Status Log Creator for submission logger."""

import logging
from typing import Any, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import VisitKeys
from outputs.error_writer import ListErrorWriter

from error_logging.error_logger import (
    ErrorLogTemplate,
    update_error_log_and_qc_metadata,
)
from error_logging.file_visit_annotator import FileVisitAnnotator

log = logging.getLogger(__name__)


class QCStatusLogCreator:
    """Creates initial QC status logs using ErrorLogTemplate."""

    def __init__(
        self, error_log_template: ErrorLogTemplate, visit_annotator: FileVisitAnnotator
    ):
        """Initialize QC status log creator.

        Args:
            error_log_template: Template for generating QC status log filenames
            visit_annotator: File visit annotator for adding visit metadata
        """
        self.__template = error_log_template
        self.__visit_annotator = visit_annotator

    def _prepare_template_record(
        self, visit_keys: VisitKeys
    ) -> Optional[dict[str, Any]]:
        """Prepare record dictionary for ErrorLogTemplate instantiation.

        Args:
            visit_keys: Visit identification information

        Returns:
            Record dictionary with field names mapped for template, or None if invalid
        """
        # Use model_dump() to get visit data
        visit_data = visit_keys.model_dump(exclude_none=True)

        # Map VisitKeys field names to ErrorLogTemplate expected field names
        record = visit_data.copy()
        if "date" in record:
            record["visitdate"] = record.pop(
                "date"
            )  # ErrorLogTemplate expects "visitdate"

        return record

    def create_qc_log(
        self,
        visit_keys: VisitKeys,
        project: ProjectAdaptor,
        gear_name: str,
        error_writer: ListErrorWriter,
    ) -> bool:
        """Creates QC status log file at project level.

        Args:
            visit_keys: Visit identification information
            project: Project adaptor for file operations
            gear_name: Name of the gear creating the log
            error_writer: Error writer for tracking any issues

        Returns:
            True if QC log creation was successful, False otherwise
        """
        if not visit_keys.ptid or not visit_keys.date or not visit_keys.module:
            log.warning(
                "Insufficient visit information to create QC log: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"module={visit_keys.module}"
            )
            return False

        # Prepare record for template instantiation
        record = self._prepare_template_record(visit_keys)
        if not record:
            log.error("Failed to prepare template record")
            return False

        # Generate QC status log filename using ErrorLogTemplate
        error_log_name = self.__template.instantiate(
            record=record, module=visit_keys.module
        )

        if not error_log_name:
            log.error(
                f"Failed to generate QC status log filename for visit: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"module={visit_keys.module}"
            )
            return False

        log.info(f"Creating QC status log: {error_log_name}")

        # Create initial QC status log with empty metadata structure
        # This initializes the log for downstream pipeline gears
        success = update_error_log_and_qc_metadata(
            error_log_name=error_log_name,
            destination_prj=project,
            gear_name=gear_name,
            state="PASS",  # Initial state for submission logger
            errors=error_writer.errors(),
            reset_qc_metadata="ALL",  # Clean slate for new submission
        )

        if success:
            log.info(f"Successfully created QC status log: {error_log_name}")

            # Add visit metadata to the QC status log file using FileVisitAnnotator
            annotation_success = self.__visit_annotator.annotate_qc_log_file(
                qc_log_filename=error_log_name,
                visit_keys=visit_keys,
            )

            if not annotation_success:
                log.warning(f"Failed to add visit metadata to QC log: {error_log_name}")
                # Don't fail the entire operation for metadata annotation failure
        else:
            log.error(f"Failed to create QC status log: {error_log_name}")

        return success

    def get_qc_log_filename(self, visit_keys: VisitKeys) -> Optional[str]:
        """Get the QC status log filename for a visit without creating it.

        Args:
            visit_keys: Visit identification information

        Returns:
            QC status log filename if it can be generated, None otherwise
        """
        if not visit_keys.ptid or not visit_keys.date or not visit_keys.module:
            return None

        # Prepare record for template instantiation
        record = self._prepare_template_record(visit_keys)
        if not record:
            return None

        return self.__template.instantiate(record=record, module=visit_keys.module)
