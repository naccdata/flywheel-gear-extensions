"""Defines Image Identifier Lookup."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import FileVisitAnnotator, QCStatusLogManager
from event_capture.event_capture import VisitEventCapture
from event_capture.visit_events import ACTION_SUBMIT, VisitEvent
from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from fw_gear import GearContext
from gear_execution.gear_execution import InputFileWrapper
from identifiers.identifiers_repository import IdentifierRepository
from keys.keys import MetadataKeys
from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import (
    QC_STATUS_FAIL,
    QC_STATUS_PASS,
    FileErrorList,
    GearTags,
    QCStatus,
)

from image_identifier_lookup_app.processor import ImageIdentifierLookupProcessor

log = logging.getLogger(__name__)


def run(
    *,
    gear_context: GearContext,
    file_path: Path,
    file_name: str,
    file_obj: FileEntry,
    input_wrapper: InputFileWrapper,
    project: ProjectAdaptor,
    subject: SubjectAdaptor,
    identifiers_repository: IdentifierRepository,
    event_capture: VisitEventCapture,
    gear_name: str,
    naccid_field_name: str,
    pipeline_adcid: int,
    ptid: str,
    existing_naccid: Optional[str],
    visit_metadata: DataIdentification,
    dicom_metadata: dict[str, Any],
) -> None:
    """Runs the Image Identifier Lookup process.

    This function orchestrates the identifier lookup workflow:
    1. Check idempotency (skip if NACCID already correct)
    2. Perform NACCID lookup if needed
    3. Update subject metadata
    4. Update QC status log
    5. Capture submission event
    6. Update file QC metadata and tags

    Args:
        gear_context: Flywheel gear context
        file_path: Path to the DICOM file
        file_name: Name of the DICOM file
        file_obj: Flywheel file object
        input_wrapper: Input file wrapper
        project: Project adaptor
        subject: Subject adaptor
        identifiers_repository: Repository for NACCID lookups
        event_capture: Event capture for submission events
        gear_name: Name of the gear
        naccid_field_name: Field name for NACCID in subject.info
        pipeline_adcid: Pre-extracted pipeline ADCID
        ptid: Pre-extracted participant identifier
        existing_naccid: Pre-extracted existing NACCID (if any)
        visit_metadata: Pre-extracted visit metadata (DataIdentification)
        dicom_metadata: Comprehensive DICOM metadata to store

    Raises:
        GearExecutionError: If processing fails
    """
    log.info(
        f"Processing file: {file_name} "
        f"(subject: {subject.label}, project: {project.label})"
    )

    # Track processing success and errors
    success = True
    errors: list = []

    # Step 1: Check idempotency - if NACCID already exists, skip lookup
    if existing_naccid:
        log.info(
            f"NACCID already exists in subject metadata: {existing_naccid}. "
            "Skipping lookup."
        )
        naccid = existing_naccid
        skipped = True
    else:
        # Step 2: Perform NACCID lookup and update subject metadata
        log.info("No existing NACCID found. Performing lookup.")
        processor = ImageIdentifierLookupProcessor(
            identifiers_repository=identifiers_repository,
            subject=subject,
            naccid_field_name=naccid_field_name,
        )

        try:
            naccid = processor.lookup_and_update(
                ptid=ptid,
                adcid=pipeline_adcid,
                existing_naccid=existing_naccid,
                dicom_metadata=dicom_metadata,
            )
            skipped = False
            log.info(f"Successfully looked up and stored NACCID: {naccid}")
        except Exception as error:
            log.error(f"Failed to lookup or update NACCID: {error}")
            success = False
            naccid = None
            skipped = False
            # Error will be captured in QC log
            raise

    log.info(f"NACCID for processing: {naccid} (skipped={skipped})")

    # Update visit_metadata with the NACCID (create new instance with updated NACCID)
    data_identification = DataIdentification.from_visit_metadata(
        ptid=ptid,
        date=visit_metadata.date,
        modality=visit_metadata.data.modality,  # type: ignore
        adcid=pipeline_adcid,
        naccid=naccid,
        visitnum=None,  # Images typically don't have visit numbers
    )

    # Step 3: Update QC status log
    log.info("Updating QC status log")
    try:
        # Initialize QC status log manager
        error_log_template = ErrorLogTemplate()
        visit_annotator = FileVisitAnnotator(project=project)
        qc_log_manager = QCStatusLogManager(
            error_log_template=error_log_template,
            visit_annotator=visit_annotator,
        )

        # Determine QC status (use QCStatus type with cast)
        qc_status: QCStatus = cast(
            QCStatus, QC_STATUS_PASS if success else QC_STATUS_FAIL
        )

        # Update QC status log
        qc_log_filename = qc_log_manager.update_qc_log(
            visit_keys=data_identification,
            project=project,
            gear_name=gear_name,
            status=qc_status,
            errors=FileErrorList(root=errors),
            add_visit_metadata=True,  # Add metadata on initial creation
        )

        if qc_log_filename:
            log.info(f"Successfully updated QC status log: {qc_log_filename}")
        else:
            log.warning("Failed to update QC status log (non-critical)")

    except Exception as error:
        # QC logging failures are non-critical - log but don't fail gear
        log.error(f"Error during QC logging (non-critical): {error}")

    # Step 4: Capture submission event
    log.info("Capturing submission event")
    try:
        visit_event = VisitEvent(
            action=ACTION_SUBMIT,
            study="adrc",
            project_label=project.label,
            center_label=project.group,  # Use group as center label
            gear_name=gear_name,
            data_identification=data_identification,
            datatype="dicom",
            timestamp=datetime.now(),
        )

        event_capture.capture_event(visit_event)
        log.info(f"Successfully captured submission event for {ptid}")

    except Exception as error:
        # Event capture failures are non-critical - log but don't fail gear
        log.error(f"Error during event capture (non-critical): {error}")

    # Step 5: Update file QC metadata and tags
    log.info("Updating file QC metadata and tags")
    try:
        # Add QC result to file metadata
        status_str = "PASS" if success else "FAIL"
        gear_context.metadata.add_qc_result(
            input_wrapper.file_input,
            name="validation",
            state=status_str,
            data=(
                FileErrorList(root=errors).model_dump(by_alias=True) if errors else None
            ),
        )

        # Set/update the validation timestamp in file.info
        timestamp = datetime.now(timezone.utc).strftime(DEFAULT_DATE_TIME_FORMAT)
        gear_context.metadata.update_file_metadata(
            input_wrapper.file_input,
            container_type=gear_context.config.destination["type"],
            info={MetadataKeys.VALIDATED_TIMESTAMP: timestamp},
        )

        # Add gear tag to file (gear-PASS or gear-FAIL)
        gear_tags = GearTags(gear_name=gear_name)
        updated_tags = gear_tags.update_tags(tags=file_obj.tags, status=status_str)
        gear_context.metadata.update_file_metadata(
            input_wrapper.file_input,
            tags=updated_tags,
            container_type=gear_context.config.destination["type"],
        )

        log.info(
            f"Successfully updated file QC metadata and tags: "
            f"{status_str} [{timestamp}]"
        )

    except Exception as error:
        # File metadata update failures are logged but don't fail gear
        log.error(f"Error updating file QC metadata (non-critical): {error}")

    log.info("Image Identifier Lookup processing completed successfully")
