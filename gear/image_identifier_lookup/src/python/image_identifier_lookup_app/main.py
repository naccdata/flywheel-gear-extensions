"""Defines Image Identifier Lookup."""

import logging
from datetime import datetime
from typing import Optional, cast

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
from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import (
    QC_STATUS_FAIL,
    QC_STATUS_PASS,
    FileErrorList,
    QCStatus,
)
from outputs.error_writer import ListErrorWriter
from outputs.errors import system_error
from s3.s3_bucket import S3InterfaceError

from image_identifier_lookup_app.extraction import LookupContext
from image_identifier_lookup_app.processor import ImageIdentifierLookupProcessor

log = logging.getLogger(__name__)


class ImageIdentifierLookup:
    """Orchestrates the identifier lookup workflow.

    Holds shared dependencies so individual steps don't need to pass
    them around. Constructed by run.py with Flywheel adaptors and
    services, then executed via run().
    """

    def __init__(
        self,
        *,
        lookup_context: LookupContext,
        project: ProjectAdaptor,
        subject: SubjectAdaptor,
        identifiers_repository: IdentifierRepository,
        event_capture: VisitEventCapture,
        gear_name: str,
        dry_run: bool = False,
        error_writer: ListErrorWriter,
    ):
        self._context = lookup_context
        self._project = project
        self._subject = subject
        self._identifiers_repository = identifiers_repository
        self._event_capture = event_capture
        self._gear_name = gear_name
        self._dry_run = dry_run
        self._error_writer = error_writer
        self._success = True
        self._naccid: Optional[str] = None

    def run(self) -> tuple[bool, FileErrorList]:
        """Execute the identifier lookup workflow.

        Steps:
        1. Resolve NACCID (use existing or perform lookup)
        2. Build data identification for QC/events
        3. Update QC status log and capture events

        Returns:
            Tuple of (success, errors)

        Raises:
            GearExecutionError: If processing fails
        """
        self._resolve_naccid()
        data_identification = self._build_data_identification()
        self._handle_post_processing(data_identification)

        log.info("Image Identifier Lookup processing completed successfully")
        return self._success, self._error_writer.errors()

    def _resolve_naccid(self) -> None:
        """Resolve NACCID — use existing or perform lookup."""
        if self._context.existing_naccid:
            log.info(
                f"NACCID already exists in subject metadata: "
                f"{self._context.existing_naccid}. Skipping lookup."
            )
            self._naccid = self._context.existing_naccid
            return

        if self._context.pipeline_adcid is None:
            raise GearExecutionError(
                "Cannot perform NACCID lookup: "
                "pipeline_adcid is not set in project metadata "
                f"for {self._project.group}/{self._project.label}"
            )

        if not self._context.ptid:
            raise GearExecutionError(
                "Cannot perform NACCID lookup: "
                "PTID not available (subject label is empty "
                "and DICOM PatientID is missing)"
            )

        log.info("No existing NACCID found. Performing lookup.")
        processor = ImageIdentifierLookupProcessor(
            identifiers_repository=self._identifiers_repository,
            subject=self._subject,
            naccid_field_name=self._context.naccid_field_name,
            dry_run=self._dry_run,
        )

        try:
            self._naccid = processor.lookup_and_update(
                ptid=self._context.ptid,
                adcid=self._context.pipeline_adcid,
                dicom_metadata=self._context.dicom_metadata or {},
            )
            log.info(f"Successfully looked up and stored NACCID: {self._naccid}")
        except (IdentifierRepositoryError, SubjectError, FlywheelError) as error:
            log.error(f"Failed to lookup or update NACCID: {error}")
            self._success = False
            self._error_writer.write(system_error(message=str(error)))

    def _build_data_identification(self) -> Optional[DataIdentification]:
        """Build DataIdentification for QC logging and event capture.

        Returns None when visit metadata is unavailable.
        """
        if self._context.visit_metadata is None:
            log.info("Visit metadata not available. Skipping QC log and event capture.")
            return None

        return DataIdentification.from_visit_metadata(
            ptid=self._context.ptid,  # type: ignore[arg-type]
            date=self._context.visit_metadata.date,
            modality=self._context.visit_metadata.data.modality,  # type: ignore
            adcid=self._context.pipeline_adcid,  # type: ignore[arg-type]
            naccid=self._naccid,
            visitnum=None,
        )

    def _handle_post_processing(
        self, data_identification: Optional[DataIdentification]
    ) -> None:
        """Handle QC status log update and event capture."""
        if self._dry_run:
            log.info("DRY RUN: Skipping QC status log update and event capture")
            return

        if data_identification is None:
            log.info("Skipping QC log and event capture (no visit metadata)")
            return

        self._update_qc_status_log(data_identification)
        self._capture_submission_event(data_identification)

    def _update_qc_status_log(self, data_identification: DataIdentification) -> None:
        """Update QC status log for the processed image.

        Note:
            Failures are logged but do not raise exceptions
            (non-critical).
        """
        log.info("Updating QC status log")
        try:
            error_log_template = ErrorLogTemplate()
            visit_annotator = FileVisitAnnotator(project=self._project)
            qc_log_manager = QCStatusLogManager(
                error_log_template=error_log_template,
                visit_annotator=visit_annotator,
            )

            qc_status: QCStatus = cast(
                QCStatus, QC_STATUS_PASS if self._success else QC_STATUS_FAIL
            )

            qc_log_filename = qc_log_manager.update_qc_log(
                visit_keys=data_identification,
                project=self._project,
                gear_name=self._gear_name,
                status=qc_status,
                errors=self._error_writer.errors(),
                add_visit_metadata=True,
            )

            if qc_log_filename:
                log.info(f"Successfully updated QC status log: {qc_log_filename}")
            else:
                log.warning("Failed to update QC status log (non-critical)")

        except (FlywheelError, ProjectError) as error:
            log.error(f"Error during QC logging (non-critical): {error}")

    def _capture_submission_event(
        self, data_identification: DataIdentification
    ) -> None:
        """Capture submission event to S3.

        Note:
            Failures are logged but do not raise exceptions
            (non-critical).
        """
        log.info("Capturing submission event")
        try:
            visit_event = VisitEvent(
                action=ACTION_SUBMIT,
                study="adrc",
                project_label=self._project.label,
                center_label=self._project.group,
                gear_name=self._gear_name,
                data_identification=data_identification,
                datatype="dicom",
                timestamp=datetime.now(),
            )

            self._event_capture.capture_event(visit_event)
            log.info(f"Successfully captured submission event for {self._context.ptid}")

        except (ClientError, S3InterfaceError) as error:
            log.error(f"Error during event capture (non-critical): {error}")
