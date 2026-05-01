"""Entry script for Pipeline Event Logger."""

import logging
from typing import Optional

from event_capture.event_capture import VisitEventCapture
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from pydantic import ValidationError
from s3.s3_bucket import S3BucketInterface

from pipeline_event_logger_app.main import PipelineEventLogger
from pipeline_event_logger_app.qc_reader import QCErrorConfig

log = logging.getLogger(__name__)


class PipelineEventLoggerVisitor(GearExecutionEnvironment):
    """Gear execution environment for Pipeline Event Logger."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        upstream_gear_name: str,
        event_capture: Optional[VisitEventCapture],
        event_actions: dict[str, str],
        error_configs: Optional[list[QCErrorConfig]] = None,
        dry_run: bool = False,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__upstream_gear_name = upstream_gear_name
        self.__event_capture = event_capture
        self.__event_actions = event_actions
        self.__error_configs = error_configs
        self.__dry_run = dry_run

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "PipelineEventLoggerVisitor":
        """Create a Pipeline Event Logger execution visitor.

        Extracts configuration:
        - upstream_gear_name: name of the upstream gear whose QC results to read
        - event_actions: mapping of QC outcome keys to event action strings
        - event_environment: environment for event capture (prod/dev)
        - event_bucket: S3 bucket name for event capture
        - error_configs: list of QCErrorConfig dicts describing how to
          extract errors from check results

        Args:
            context: The gear context
            parameter_store: The parameter store (unused)

        Returns:
            The execution environment

        Raises:
            GearExecutionError: If required configuration is missing or invalid
        """
        client = ContextClient.create(context=context)

        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "missing expected input, input_file"

        options = context.config.opts
        upstream_gear_name = options.get("upstream_gear_name")
        if not upstream_gear_name:
            raise GearExecutionError(
                "upstream_gear_name is a required configuration parameter"
            )

        event_actions: dict[str, str] = options.get("event_actions", {})
        event_environment = options.get("event_environment")
        event_bucket_name = options.get("event_bucket")
        dry_run = options.get("dry_run", False)

        # Parse error extraction configs
        error_configs = _parse_error_configs(options.get("error_configs"))

        event_capture = None
        if event_actions:
            if not event_environment or not event_bucket_name:
                raise GearExecutionError(
                    "event_actions is non-empty but event_environment "
                    "and event_bucket are required"
                )

            event_bucket = S3BucketInterface.create_from_environment(event_bucket_name)
            event_capture = VisitEventCapture(
                s3_bucket=event_bucket, environment=event_environment
            )
            log.info(
                "Event capture initialized for environment '%s' with bucket '%s'",
                event_environment,
                event_bucket_name,
            )

        return PipelineEventLoggerVisitor(
            client=client,
            file_input=file_input,
            upstream_gear_name=upstream_gear_name,
            event_capture=event_capture,
            event_actions=event_actions,
            error_configs=error_configs,
            dry_run=dry_run,
        )

    def run(self, context: GearContext) -> None:
        """Main execution method.

        1. Retrieve input file from Flywheel
        2. Retrieve parent project
        3. Delegate to PipelineEventLogger business logic

        Args:
            context: The gear execution context

        Raises:
            GearExecutionError: If required data is missing
        """
        log.info("Starting Pipeline Event Logger processing")

        try:
            file_obj = self.proxy.get_file(self.__file_input.file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        fw_project = self.proxy.get_project_by_id(file_obj.parents.project)
        if not fw_project:
            raise GearExecutionError(
                f"Failed to retrieve parent project for file {file_obj.name}"
            )
        project = ProjectAdaptor(project=fw_project, proxy=self.proxy)

        PipelineEventLogger(
            file_entry=file_obj,
            project=project,
            upstream_gear_name=self.__upstream_gear_name,
            event_capture=self.__event_capture,
            event_actions=self.__event_actions,
            error_configs=self.__error_configs,
            dry_run=self.__dry_run,
        ).run()


def _parse_error_configs(
    raw_configs: Optional[list[dict]],
) -> Optional[list[QCErrorConfig]]:
    """Parse error_configs from gear configuration.

    Args:
        raw_configs: Raw list of config dicts from gear options, or None.

    Returns:
        List of validated QCErrorConfig objects, or None if not configured.

    Raises:
        GearExecutionError: If config is present but invalid.
    """
    if not raw_configs:
        return None

    try:
        return [QCErrorConfig.model_validate(cfg) for cfg in raw_configs]
    except ValidationError as error:
        raise GearExecutionError(
            f"Invalid error_configs configuration: {error}"
        ) from error


def main():
    """Main method for Pipeline Event Logger."""
    GearEngine().run(gear_type=PipelineEventLoggerVisitor)


if __name__ == "__main__":
    main()
