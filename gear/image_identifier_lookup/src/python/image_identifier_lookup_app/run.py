"""Entry script for Image Identifier Lookup."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from botocore.exceptions import ClientError
from dates.form_dates import DEFAULT_DATE_TIME_FORMAT
from event_capture.event_capture import VisitEventCapture
from flywheel_adaptor.flywheel_proxy import FlywheelError, ProjectAdaptor
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from inputs.parameter_store import ParameterStore
from keys.keys import MetadataKeys
from lambdas.lambda_function import LambdaClient, create_lambda_client
from nacc_common.error_models import FileErrorList, GearTags
from outputs.error_writer import ListErrorWriter
from s3.s3_bucket import S3BucketInterface

from image_identifier_lookup_app.extraction import extract_dicom_metadata
from image_identifier_lookup_app.main import run

log = logging.getLogger(__name__)


class ImageIdentifierLookupVisitor(GearExecutionEnvironment):
    """Visitor for the Image Identifier Lookup gear."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        identifiers_repository: IdentifiersLambdaRepository,
        event_capture: VisitEventCapture,
        gear_name: str,
        dry_run: bool = False,
        naccid_field_name: str = "naccid",
    ):
        """Initialize the visitor with dependencies.

        Args:
            client: Flywheel SDK client wrapper
            file_input: Gear input file wrapper
            identifiers_repository: Repository for NACCID lookups
            event_capture: Event capture for submission events
            gear_name: Name of the gear
            dry_run: Whether to perform a dry run (no metadata updates)
            naccid_field_name: Field name for NACCID in subject.info
        """
        super().__init__(client=client)
        self.__file_input = file_input
        self.__identifiers_repository = identifiers_repository
        self.__event_capture = event_capture
        self.__gear_name = gear_name
        self.__dry_run = dry_run
        self.__naccid_field_name = naccid_field_name

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "ImageIdentifierLookupVisitor":
        """Creates an Image Identifier Lookup execution visitor.

        Extracts configuration:
        - database_mode: prod/dev for identifier repository
        - naccid_field_name: subject metadata field name (default: "naccid")
        - event_environment: environment prefix for event capture (required)
        - event_bucket: S3 bucket for event storage (required)

        Initializes:
        - ClientWrapper (GearBotClient)
        - InputFileWrapper for input_file
        - IdentifiersLambdaRepository
        - VisitEventCapture (required - fails if event_environment or
          event_bucket missing)

        QCStatusLogManager is initialized in run() method when project context
        is available.

        Args:
            context: The gear context
            parameter_store: The parameter store
        Returns:
            The execution environment
        Raises:
            GearExecutionError if any expected inputs are missing or if
                event capture configuration is invalid
        """
        assert parameter_store, "Parameter store expected"

        # Initialize client
        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        # Get input file
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "missing expected input, input_file"

        # Extract configuration
        options = context.config.opts
        dry_run = options.get("dry_run", False)
        database_mode = options.get("database_mode", "prod")
        naccid_field_name = options.get("naccid_field_name", "naccid")
        event_environment = options.get("event_environment")
        event_bucket_name = options.get("event_bucket")

        gear_name = cls.get_gear_name(context, "image-identifier-lookup")

        # Validate event capture configuration (required)
        if not event_environment or not event_bucket_name:
            raise GearExecutionError(
                "event_environment and event_bucket are required configuration "
                "parameters for event capture"
            )

        # Initialize identifiers repository
        identifiers_repository = IdentifiersLambdaRepository(
            client=LambdaClient(client=create_lambda_client()),
            mode=database_mode,
        )

        # Initialize event capture (required) - verify S3 bucket accessibility
        try:
            event_bucket = S3BucketInterface.create_from_environment(event_bucket_name)
            event_capture = VisitEventCapture(
                s3_bucket=event_bucket, environment=event_environment
            )
            log.info(
                f"Event capture initialized for environment '{event_environment}' "
                f"with bucket '{event_bucket_name}'"
            )
        except ClientError as error:
            raise GearExecutionError(
                f"Failed to initialize event capture: Unable to access S3 bucket "
                f"'{event_bucket_name}'. Error: {error}"
            ) from error

        return ImageIdentifierLookupVisitor(
            client=client,
            file_input=file_input,
            identifiers_repository=identifiers_repository,
            event_capture=event_capture,
            gear_name=gear_name,
            dry_run=dry_run,
            naccid_field_name=naccid_field_name,
        )

    def run(self, context: GearContext) -> None:
        """Main execution method.

        1. Retrieve input file, parent subject, and project
        2. Call main.run() to orchestrate the workflow
        3. Update file QC metadata and tags

        Args:
            context: The gear execution context

        Raises:
            GearExecutionError: If any required data is missing or processing fails
        """
        log.info("Starting Image Identifier Lookup processing")

        # Step 1: Retrieve input file, parent subject, and project
        log.info("Retrieving input file and parent containers")
        file_obj = self.proxy.get_file(self.__file_input.file_id)
        file_path = Path(self.__file_input.filepath)

        fw_project = self.proxy.get_project_by_id(file_obj.parents.project)
        if not fw_project:
            raise GearExecutionError(
                f"Failed to retrieve parent project for file {file_obj.name}"
            )
        project = ProjectAdaptor(project=fw_project, proxy=self.proxy)

        subject = project.get_subject_by_id(file_obj.parents.subject)
        if not subject:
            raise GearExecutionError(
                f"Failed to retrieve parent subject for file {file_obj.name}"
            )

        log.info(
            f"Processing file: {file_obj.name} "
            f"(subject: {subject.label}, project: {project.label})"
        )

        # Step 2: Extract DICOM metadata once (fail fast if invalid DICOM)
        log.info("Extracting DICOM metadata")
        dicom_metadata = extract_dicom_metadata(file_path)

        # Step 3: Call main.run() to orchestrate the workflow
        file_id = self.__file_input.file_id
        error_writer = ListErrorWriter(
            container_id=file_id,
            fw_path=self.proxy.get_lookup_path(file_obj),
        )

        success, errors = run(
            project=project,
            subject=subject,
            identifiers_repository=self.__identifiers_repository,
            event_capture=self.__event_capture,
            gear_name=self.__gear_name,
            dry_run=self.__dry_run,
            naccid_field_name=self.__naccid_field_name,
            dicom_metadata=dicom_metadata,
            error_writer=error_writer,
        )

        # Step 4: Update file QC metadata and tags
        log.info("Updating file QC metadata and tags")
        self._update_file_metadata(
            context=context,
            file_obj=file_obj,
            success=success,
            errors=errors,
        )

    def _update_file_metadata(
        self,
        *,
        context: GearContext,
        file_obj,
        success: bool,
        errors: FileErrorList,
    ) -> None:
        """Update file QC metadata and tags.

        This method updates the file with:
        - QC result (PASS/FAIL)
        - Validation timestamp
        - Gear tags

        Args:
            context: Gear context
            file_obj: Flywheel file object
            success: Whether processing succeeded
            errors: Accumulated file errors

        Note:
            Failures in this method are logged but do not fail the gear
            as metadata updates are considered non-critical.
        """
        try:
            # Add QC result to file metadata
            status_str = "PASS" if success else "FAIL"
            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state=status_str,
                data=(errors.model_dump(by_alias=True) if errors else None),
            )

            # Set/update the validation timestamp in file.info
            timestamp = datetime.now(timezone.utc).strftime(DEFAULT_DATE_TIME_FORMAT)
            context.metadata.update_file_metadata(
                self.__file_input.file_input,
                container_type=context.config.destination["type"],
                info={MetadataKeys.VALIDATED_TIMESTAMP: timestamp},
            )

            # Add gear tag to file (gear-PASS or gear-FAIL)
            gear_tags = GearTags(gear_name=self.__gear_name)
            updated_tags = gear_tags.update_tags(tags=file_obj.tags, status=status_str)
            context.metadata.update_file_metadata(
                self.__file_input.file_input,
                tags=updated_tags,
                container_type=context.config.destination["type"],
            )

            log.info(
                f"Successfully updated file QC metadata and tags: "
                f"{status_str} [{timestamp}]"
            )

        except FlywheelError as error:
            # File metadata update failures are logged but don't fail gear
            log.error(f"Error updating file QC metadata (non-critical): {error}")


def main():
    """Main method for Image Identifier Lookup."""

    GearEngine().run(gear_type=ImageIdentifierLookupVisitor)


if __name__ == "__main__":
    main()
