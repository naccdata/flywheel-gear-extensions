"""Defines Image Identifier Lookup."""

import logging
from datetime import datetime
from typing import cast

from botocore.exceptions import ClientError
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import FileVisitAnnotator, QCStatusLogManager
from event_capture.event_capture import VisitEventCapture
from event_capture.visit_events import ACTION_SUBMIT, VisitEvent
from flywheel_adaptor.flywheel_proxy import FlywheelError, ProjectAdaptor, ProjectError
from flywheel_adaptor.subject_adaptor import SubjectAdaptor, SubjectError
from gear_execution.gear_execution import GearExecutionError
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from nacc_common.data_identification import DataIdentification, ImageIdentification
from nacc_common.error_models import (
    QC_STATUS_FAIL,
    QC_STATUS_PASS,
    FileErrorList,
    QCStatus,
)
from s3.s3_bucket import S3InterfaceError

from image_identifier_lookup_app.dicom_utils import InvalidDicomError
from image_identifier_lookup_app.extraction import (
    extract_existing_naccid,
    extract_pipeline_adcid,
    extract_ptid,
    extract_visit_metadata,
)
from image_identifier_lookup_app.processor import ImageIdentifierLookupProcessor

log = logging.getLogger(__name__)


def run(
    *,
    project: ProjectAdaptor,
    subject: SubjectAdaptor,
    identifiers_repository: IdentifierRepository,
    event_capture: VisitEventCapture,
    gear_name: str,
    naccid_field_name: str,
    default_modality: str,
    dicom_metadata: dict,
) -> tuple[bool, list]:
    """Runs the Image Identifier Lookup process.

    This function orchestrates the identifier lookup workflow:
    1. Extract all required data early (fail fast)
    2. Check idempotency (skip if NACCID already correct)
    3. Perform NACCID lookup if needed
    4. Update subject metadata
    5. Update QC status log
    6. Capture submission event

    Args:
        project: Project adaptor
        subject: Subject adaptor
        identifiers_repository: Repository for NACCID lookups
        event_capture: Event capture for submission events
        gear_name: Name of the gear
        naccid_field_name: Field name for NACCID in subject.info
        default_modality: Default modality if DICOM tag missing
        dicom_metadata: Pre-extracted DICOM metadata dictionary

    Returns:
        Tuple of (success: bool, errors: list)

    Raises:
        GearExecutionError: If processing fails
    """

    # Step 1: Extract all required data early (fail fast)
    log.info("Extracting required data from project, subject, and DICOM metadata")

    try:
        # Extract pipeline ADCID from project metadata
        pipeline_adcid = extract_pipeline_adcid(project)
        log.info(f"Extracted pipeline ADCID: {pipeline_adcid}")

        # Extract PTID from subject.label or DICOM PatientID
        ptid = extract_ptid(subject, dicom_metadata)
        log.info(f"Extracted PTID: {ptid}")

        # Extract existing NACCID from subject.info (if present)
        existing_naccid = extract_existing_naccid(subject, naccid_field_name)
        if existing_naccid:
            log.info(f"Found existing NACCID in subject metadata: {existing_naccid}")
        else:
            log.info("No existing NACCID found in subject metadata")

        # Extract visit metadata from DICOM (StudyDate, modality)
        # Note: Pass None for naccid initially, will be updated after lookup
        visit_metadata = extract_visit_metadata(
            dicom_metadata=dicom_metadata,
            ptid=ptid,
            adcid=pipeline_adcid,
            naccid=existing_naccid,
            default_modality=default_modality,
        )
        # Type assertion: we know this is ImageIdentification
        assert isinstance(visit_metadata.data, ImageIdentification)
        log.info(
            f"Extracted visit metadata - date: {visit_metadata.date}, "
            f"modality: {visit_metadata.data.modality}"
        )

        log.info(
            f"Using pre-extracted DICOM metadata with {len(dicom_metadata)} fields "
            f"(StudyInstanceUID: {dicom_metadata.get('study_instance_uid', 'N/A')})"
        )

    except ValueError as error:
        # Missing required data - fail fast
        log.error(f"Failed to extract required data: {error}")
        raise GearExecutionError(f"Data extraction failed: {error}") from error
    except InvalidDicomError as error:
        # Invalid or unparseable DICOM file
        log.error(f"Invalid DICOM file: {error}")
        raise GearExecutionError(f"DICOM parsing failed: {error}") from error
    except ProjectError as error:
        # Project metadata issues (e.g., missing ADCID)
        log.error(f"Project metadata error: {error}")
        raise GearExecutionError(f"Project configuration error: {error}") from error

    log.info("Early data extraction completed successfully")

    # Track processing success and errors
    success = True
    errors: list = []

    # Step 2: Check idempotency - if NACCID already exists, skip lookup
    if existing_naccid:
        log.info(
            f"NACCID already exists in subject metadata: {existing_naccid}. "
            "Skipping lookup."
        )
        naccid = existing_naccid
        skipped = True
    else:
        # Step 3: Perform NACCID lookup and update subject metadata
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
        except (IdentifierRepositoryError, SubjectError, FlywheelError) as error:
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

    # Step 4: Update QC status log
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

    except (FlywheelError, ProjectError) as error:
        # QC logging failures are non-critical - log but don't fail gear
        log.error(f"Error during QC logging (non-critical): {error}")

    # Step 5: Capture submission event
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

    except (ClientError, S3InterfaceError) as error:
        # Event capture failures are non-critical - log but don't fail gear
        log.error(f"Error during event capture (non-critical): {error}")

    log.info("Image Identifier Lookup processing completed successfully")

    return success, errors
