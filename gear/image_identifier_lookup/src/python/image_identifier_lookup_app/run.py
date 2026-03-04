"""Entry script for Image Identifier Lookup."""

import logging
from typing import Optional

from botocore.exceptions import ClientError
from event_capture.event_capture import VisitEventCapture
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
from lambdas.lambda_function import LambdaClient, create_lambda_client
from s3.s3_bucket import S3BucketInterface

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
        naccid_field_name: str = "naccid",
        default_modality: str = "UNKNOWN",
    ):
        """Initialize the visitor with dependencies.

        Args:
            client: Flywheel SDK client wrapper
            file_input: Gear input file wrapper
            identifiers_repository: Repository for NACCID lookups
            event_capture: Event capture for submission events
            gear_name: Name of the gear
            naccid_field_name: Field name for NACCID in subject.info
            default_modality: Default modality if DICOM tag missing
        """
        super().__init__(client=client)
        self.__file_input = file_input
        self.__identifiers_repository = identifiers_repository
        self.__event_capture = event_capture
        self.__gear_name = gear_name
        self.__naccid_field_name = naccid_field_name
        self.__default_modality = default_modality

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
        - default_modality: fallback modality (default: "UNKNOWN")
        - event_environment: environment prefix for event capture (required)
        - event_bucket: S3 bucket for event storage (required)
        - admin_group: NACC admin group ID (default: "nacc")

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
        database_mode = options.get("database_mode", "prod")
        naccid_field_name = options.get("naccid_field_name", "naccid")
        default_modality = options.get("default_modality", "UNKNOWN")
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
            naccid_field_name=naccid_field_name,
            default_modality=default_modality,
        )

    def run(self, context: GearContext) -> None:
        """Main execution method.

        1. Retrieve input file, parent subject, and project
        2. Extract all required data early (fail fast)
        3. Check idempotency: if NACCID already exists, skip to step 6
        4. Perform NACCID lookup
        5. Update subject metadata with NACCID and DICOM metadata
        6. Update QC status log
        7. Capture submission event (required)
        8. Update file QC metadata and tags

        Args:
            context: The gear execution context
        """
        run(proxy=self.proxy)


def main():
    """Main method for Image Identifier Lookup."""

    GearEngine().run(gear_type=ImageIdentifierLookupVisitor)


if __name__ == "__main__":
    main()
