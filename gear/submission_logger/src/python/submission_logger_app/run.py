"""Entry script for Submission Logger."""

import logging
from typing import Optional

from event_logging.event_logging import VisitEventLogger
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from pydantic import ValidationError
from s3.s3_bucket import S3BucketInterface
from utils.utils import load_form_ingest_configurations

from submission_logger_app.main import run

log = logging.getLogger(__name__)


class SubmissionLoggerVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the submission logger app."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        config_input: Optional[InputFileWrapper],
        gear_name: str,
        event_logger: VisitEventLogger,
        environment: str,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__config_input = config_input
        self.__gear_name = gear_name
        self.__event_logger = event_logger
        self.__environment = environment

    @classmethod
    def create(
        cls, context: GearToolkitContext, parameter_store: Optional[ParameterStore]
    ) -> "SubmissionLoggerVisitor":
        """Creates a submission logger execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Raises:
          GearExecutionError if required inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing input file"

        config_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )

        gear_name = context.manifest.get("name", "submission-logger")
        environment = context.config.get("environment", "prod")
        event_bucket = context.config.get("event_bucket", "nacc-event-logs")

        # Create S3 bucket interface for event logging
        s3_bucket = S3BucketInterface.create_from_environment(event_bucket)
        if not s3_bucket:
            raise GearExecutionError(f"Unable to access S3 bucket {event_bucket}")

        event_logger = VisitEventLogger(s3_bucket=s3_bucket, environment=environment)

        return SubmissionLoggerVisitor(
            client=client,
            file_input=file_input,
            config_input=config_input,
            gear_name=gear_name,
            event_logger=event_logger,
            environment=environment,
        )

    def run(self, context: GearToolkitContext) -> None:
        """Runs the submission logger app.

        Args:
            context: the gear execution context
        """
        assert context, "Gear context required"

        # Create error writer for tracking processing errors
        from outputs.error_writer import ListErrorWriter

        file_id = self.__file_input.file_id
        error_writer = ListErrorWriter(
            container_id=file_id,
            fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
        )

        # Load form project configurations if provided
        form_project_configs = None
        module = None

        if self.__config_input:
            try:
                form_project_configs = load_form_ingest_configurations(
                    self.__config_input.filepath
                )
            except ValidationError as error:
                raise GearExecutionError(
                    f"Error reading form configurations file "
                    f"{self.__config_input.filename}: {error}"
                ) from error

            # Get module from gear configuration
            module = context.config.get("module", "").upper()
            if not module:
                raise GearExecutionError(
                    "Module configuration is required when form_configs_file is provided"
                )

            # Validate module is supported
            if (
                module not in form_project_configs.accepted_modules
                or not form_project_configs.module_configs.get(module)
            ):
                raise GearExecutionError(
                    f"Failed to find the configurations for module {module}"
                )

        success = run(
            file_input=self.__file_input,
            event_logger=self.__event_logger,
            gear_name=self.__gear_name,
            proxy=self.proxy,
            context=context,
            error_writer=error_writer,
            form_project_configs=form_project_configs,
            module=module,
        )

        # Add QC result following identifier_lookup pattern
        context.metadata.add_qc_result(
            self.__file_input.file_input,
            name="validation",
            state="PASS" if success else "FAIL",
            data=error_writer.errors().model_dump(by_alias=True),
        )

        # Add file tags following identifier_lookup pattern
        context.metadata.add_file_tags(
            self.__file_input.file_input, tags=self.__gear_name
        )


def main():
    """Main method for Submission Logger."""

    GearEngine.create_with_parameter_store().run(gear_type=SubmissionLoggerVisitor)


if __name__ == "__main__":
    main()
