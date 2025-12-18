"""QC Status Log Creator and File Visit Annotator."""

import logging
from typing import Any, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import FileErrorList, QCStatus, VisitKeys, VisitMetadata

from error_logging.error_logger import (
    ErrorLogTemplate,
    MetadataCleanupFlag,
    update_error_log_and_qc_metadata,
    update_file_info,
)

log = logging.getLogger(__name__)


class FileVisitAnnotator:
    """Annotates QC status log files with visit metadata.

    Each QC status log file corresponds to a specific visit found during
    single-file processing.
    """

    def __init__(self, project: ProjectAdaptor):
        """Initialize file visit annotator.

        Args:
            project: Project adaptor for file operations
        """
        self.__project = project

    def annotate_qc_log_file(
        self, qc_log_filename: str, visit_metadata: VisitMetadata
    ) -> bool:
        """Add visit metadata to a QC status log file.

        Args:
            qc_log_filename: Name of the QC status log file
            visit_metadata: Visit metadata information for this specific visit

        Returns:
            True if visit annotation was successful, False otherwise
        """
        if (
            not visit_metadata.ptid
            or not visit_metadata.date
            or not visit_metadata.module
        ):
            log.warning(
                f"Insufficient visit data for annotation: "
                f"ptid={visit_metadata.ptid}, date={visit_metadata.date}, "
                f"module={visit_metadata.module}"
            )
            return False

        try:
            # Get the QC status log file
            qc_log_file = self.__project.get_file(qc_log_filename)
            if not qc_log_file:
                log.error(f"QC status log file not found: {qc_log_filename}")
                return False

            # Prepare visit metadata for this specific visit
            visit_metadata_dict = self._create_visit_metadata(visit_metadata)

            # Update file info with visit metadata using retry-enabled method
            info_update = {"visit": visit_metadata_dict}
            update_file_info(file=qc_log_file, custom_info=info_update)

            log.info(f"Added visit metadata to QC log: {qc_log_filename}")
            return True

        except Exception as error:
            log.error(
                f"Failed to add visit metadata to QC log {qc_log_filename}: {error}"
            )
            return False

    def _create_visit_metadata(self, visit_metadata: VisitMetadata) -> dict[str, Any]:
        """Create visit metadata dictionary for a single visit.

        Args:
            visit_metadata: Visit metadata information

        Returns:
            Visit metadata dictionary
        """
        # Use Pydantic model_dump() to serialize the VisitMetadata directly
        return visit_metadata.model_dump(exclude_none=True)


class QCStatusLogManager:
    """Manages QC status logs using ErrorLogTemplate for both creation and
    updates."""

    def __init__(
        self, error_log_template: ErrorLogTemplate, visit_annotator: FileVisitAnnotator
    ):
        """Initialize QC status log manager.

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

    def update_qc_log(
        self,
        visit_keys: VisitKeys,
        project: ProjectAdaptor,
        gear_name: str,
        status: QCStatus,
        errors: FileErrorList,
        reset_qc_metadata: MetadataCleanupFlag = "NA",
        add_visit_metadata: bool = False,
    ) -> bool:
        """Updates or creates QC status log file at project level.

        Args:
            visit_keys: Visit identification information
            project: Project adaptor for file operations
            gear_name: Name of the gear updating the log
            status: QC status (PASS, FAIL, IN REVIEW)
            errors: Error list for the gear
            reset_qc_metadata: Metadata reset strategy (ALL, GEAR, NA)
            add_visit_metadata: Whether to add visit metadata (for initial creation)

        Returns:
            True if QC log update was successful, False otherwise
        """
        if not visit_keys.ptid or not visit_keys.date or not visit_keys.module:
            log.warning(
                "Insufficient visit information to update QC log: "
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

        log.info(f"Updating QC status log: {error_log_name}")

        # Update QC status log with gear results
        success = update_error_log_and_qc_metadata(
            error_log_name=error_log_name,
            destination_prj=project,
            gear_name=gear_name,
            state=status,
            errors=errors,
            reset_qc_metadata=reset_qc_metadata,
        )

        if success:
            log.info(f"Successfully updated QC status log: {error_log_name}")

            # Add visit metadata if requested (for initial creation)
            if add_visit_metadata:
                # Convert VisitKeys to VisitMetadata for annotation
                if isinstance(visit_keys, VisitMetadata):
                    visit_metadata = visit_keys
                else:
                    # Create VisitMetadata from VisitKeys (packet will be None)
                    visit_metadata = VisitMetadata(**visit_keys.model_dump())

                annotation_success = self.__visit_annotator.annotate_qc_log_file(
                    qc_log_filename=error_log_name,
                    visit_metadata=visit_metadata,
                )

                if not annotation_success:
                    log.warning(
                        f"Failed to add visit metadata to QC log: {error_log_name}"
                    )
                    # Don't fail the entire operation for metadata annotation failure
        else:
            log.error(f"Failed to update QC status log: {error_log_name}")

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
