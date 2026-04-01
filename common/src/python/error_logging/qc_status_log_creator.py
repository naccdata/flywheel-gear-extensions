"""QC Status Log Creator and File Visit Annotator."""

import logging
from typing import Any, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import FileErrorList, FileQCModel, QCStatus
from pydantic import ValidationError

from error_logging.error_logger import (
    ErrorLogTemplate,
    MetadataCleanupFlag,
    get_log_contents,
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
        self, qc_log_filename: str, visit_metadata: DataIdentification
    ) -> bool:
        """Add visit metadata to a QC status log file.

        Args:
            qc_log_filename: Name of the QC status log file
            visit_metadata: Visit metadata information for this specific visit

        Returns:
            True if visit annotation was successful, False otherwise
        """
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

    def _create_visit_metadata(
        self, visit_metadata: DataIdentification
    ) -> dict[str, Any]:
        """Create visit metadata dictionary for a single visit.

        Args:
            visit_metadata: Visit metadata information

        Returns:
            Visit metadata dictionary
        """
        # Use model_dump with mode="raw" to get raw field names without transformation
        return visit_metadata.model_dump(exclude_none=True, mode="raw")


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

    def get_qc_log_filename(
        self, visit_keys: DataIdentification, project: ProjectAdaptor
    ) -> Optional[str]:
        """Get the actual QC status log filename that exists or would be
        created.

        Checks for existing files in both new and legacy formats, returning
        whichever exists. If neither exists, returns the new format filename
        that would be created.

        Args:
            visit_keys: Visit identification information
            project: Project adaptor for checking file existence

        Returns:
            The filename that exists or would be created,
            None if filename cannot be generated
        """
        # Generate new format filename
        new_format_filename = self.__template.instantiate(visit_keys)
        if not new_format_filename:
            return None

        # Check if new format file exists
        existing_file = project.get_file(new_format_filename)
        if existing_file:
            return new_format_filename

        # Generate legacy format filename
        legacy_filename = self.__template.instantiate_legacy(visit_keys)

        # Check if legacy format file exists
        if legacy_filename and legacy_filename != new_format_filename:
            legacy_file = project.get_file(legacy_filename)
            if legacy_file:
                # copy to the new naming format and delete the existing log file
                return self.replace_legacy_log_file(
                    legacy_file=legacy_file,
                    new_log_name=new_format_filename,
                    project=project,
                )

        # Neither exists, return new format (what would be created)
        return new_format_filename

    def update_qc_log(
        self,
        visit_keys: DataIdentification,
        project: ProjectAdaptor,
        gear_name: str,
        status: QCStatus,
        errors: FileErrorList,
        reset_qc_metadata: MetadataCleanupFlag = "NA",
        add_visit_metadata: bool = False,
    ) -> Optional[str]:
        """Updates or creates QC status log file at project level.

        Handles both new format (with visitnum/packet) and legacy format
        (without visitnum/packet) filenames. When updating an existing file,
        tries new format first, then legacy format. When creating a new file,
        uses new format only.

        Args:
            visit_keys: Visit identification information
            project: Project adaptor for file operations
            gear_name: Name of the gear updating the log
            status: QC status (PASS, FAIL, IN REVIEW)
            errors: Error list for the gear
            reset_qc_metadata: Metadata reset strategy (ALL, GEAR, NA)
            add_visit_metadata: Whether to add visit metadata (for initial creation)

        Returns:
            The QC log filename if update was successful, None otherwise
        """
        # Get the actual filename to use (checks for existing files in both formats)
        error_log_name = self.get_qc_log_filename(visit_keys, project)
        if not error_log_name:
            log.error(
                f"Failed to generate QC status log filename for visit: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"module={visit_keys.module}"
            )
            return None

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
                # visit_keys is already DataIdentification (VisitKeys is an alias)
                visit_metadata = visit_keys

                annotation_success = self.__visit_annotator.annotate_qc_log_file(
                    qc_log_filename=error_log_name,
                    visit_metadata=visit_metadata,
                )

                if not annotation_success:
                    log.warning(
                        f"Failed to add visit metadata to QC log: {error_log_name}"
                    )
                    # Don't fail the entire operation for metadata annotation failure

            return error_log_name
        else:
            log.error(f"Failed to update QC status log: {error_log_name}")
            return None

    def replace_legacy_log_file(
        self, *, legacy_file: FileEntry, new_log_name: str, project: ProjectAdaptor
    ) -> str:
        """Replace the legacy error log file with new naming format. Copy the
        contents of legacy file to a new file and delete the existing file.

        Args:
            legacy_file: existing log file object
            new_log_name: log file name in new format
            project: Flywheel project adaptor

        Returns:
            Log filename in new format if replace was successful, else old filename
        """

        contents = get_log_contents(legacy_file)
        qc_info: Optional[FileQCModel] = FileQCModel(qc={})

        try:
            qc_info = FileQCModel.create(legacy_file)
        except ValidationError as error:
            log.warning(
                "Error loading QC metadata for file %s: %s", legacy_file.name, error
            )

        new_file = project.upload_file_contents(
            filename=new_log_name, contents=contents, content_type="text"
        )

        if new_file is None:
            return legacy_file.name

        try:
            update_file_info(
                file=new_file, custom_info=qc_info.model_dump(by_alias=True)
            )
        except ApiException as error:
            log.warning(
                f"Error in setting QC metadata in log file {new_log_name}: {error}"
            )

        project.delete_file(legacy_file.name)

        return new_log_name
