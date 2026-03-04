"""Defines Image Identifier Lookup."""

import logging
from pathlib import Path
from typing import Any, Optional

from event_capture.event_capture import VisitEventCapture
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.identifiers_repository import IdentifierRepository

from image_identifier_lookup_app.processor import ImageIdentifierLookupProcessor

log = logging.getLogger(__name__)


def run(
    *,
    file_path: Path,
    file_name: str,
    project: ProjectAdaptor,
    subject: SubjectAdaptor,
    identifiers_repository: IdentifierRepository,
    event_capture: VisitEventCapture,
    gear_name: str,
    naccid_field_name: str,
    pipeline_adcid: int,
    ptid: str,
    existing_naccid: Optional[str],
    visit_metadata: Any,
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
        file_path: Path to the DICOM file
        file_name: Name of the DICOM file
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

        naccid = processor.lookup_and_update(
            ptid=ptid,
            adcid=pipeline_adcid,
            existing_naccid=existing_naccid,
            dicom_metadata=dicom_metadata,
        )
        skipped = False

    log.info(f"NACCID for processing: {naccid} (skipped={skipped})")

    # TODO: Step 3: Update QC status log (task 3.4)
    # TODO: Step 4: Capture submission event (task 3.4)
    # TODO: Step 5: Update file QC metadata and tags (task 3.5)

    log.info("Image Identifier Lookup processing completed successfully")
