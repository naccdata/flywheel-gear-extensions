"""Entry script for form_scheduler."""

import logging
from typing import Any, Optional

from configs.ingest_configs import ConfigsError, PipelineConfigs
from event_logging.event_logging import VisitEventLogger
from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import (
    ParameterError,
    ParameterStore,
    URLParameter,
)
from jobs.job_poll import JobPoll
from notifications.email import EmailClient, create_ses_client
from s3.s3_bucket import S3BucketInterface

from form_scheduler_app.main import run

log = logging.getLogger(__name__)


class FormSchedulerVisitor(GearExecutionEnvironment):
    """Visitor for the Form Scheduler gear."""

    def __init__(
        self,
        client: ClientWrapper,
        pipeline_configs_input: InputFileWrapper,
        form_configs_input: InputFileWrapper,
        event_bucket: S3BucketInterface,
        source_email: Optional[str] = None,
        portal_url: Optional[URLParameter] = None,
    ):
        super().__init__(client=client)

        self.__configs_input = pipeline_configs_input
        self.__form_configs_input = form_configs_input
        self.__source_email = source_email
        self.__portal_url = portal_url
        self.__event_bucket = event_bucket

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "FormSchedulerVisitor":
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        pipeline_configs_input = InputFileWrapper.create(
            input_name="pipeline_configs_file", context=context
        )
        assert pipeline_configs_input, "missing expected input, pipeline_configs_file"

        form_configs_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )
        assert form_configs_input, "missing expected input, form_configs_file"

        source_email = context.config.get("source_email", "nacchelp@uw.edu")

        portal_url = None
        if source_email:
            try:
                portal_path = context.config.get("portal_url_path", None)
                if not portal_path:
                    raise GearExecutionError(
                        "No portal URL found, required " + "to send emails"
                    )
                portal_url = parameter_store.get_portal_url(portal_path)  # type: ignore
            except ParameterError as error:
                raise GearExecutionError(f"Parameter error: {error}") from error

        event_bucket_name = context.config.get("event_bucket", None)
        if event_bucket_name is None:
            raise GearExecutionError("event bucket name is required")
        event_bucket = S3BucketInterface.create_from_environment(event_bucket_name)

        return FormSchedulerVisitor(
            client=client,
            pipeline_configs_input=pipeline_configs_input,
            form_configs_input=form_configs_input,
            event_bucket=event_bucket,
            source_email=source_email,
            portal_url=portal_url,
        )

    def run(self, context: GearToolkitContext) -> None:
        """Runs the Form Scheduler app."""
        try:
            dest_container: Any = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f"Cannot find destination container: {error}"
            ) from error

        if dest_container.container_type != "project":
            raise GearExecutionError(
                f"Unsupported container type {dest_container.container_type}, "
                f"this gear must be executed at project level"
            )

        project_id = dest_container.id

        # check for other form-scheduler gear jobs running on this project
        # there shouldn't be any
        gear_name = context.manifest.get("name", "form-scheduler")
        job_id = context.config_json.get("job", {}).get("id")
        if JobPoll.is_another_gear_instance_running(
            proxy=self.proxy,
            gear_name=gear_name,
            project_id=project_id,
            current_job=job_id,
        ):
            raise GearExecutionError(
                "Another Form Scheduler gear already running on this project"
            )

        try:
            pipeline_configs = PipelineConfigs.load_form_pipeline_configurations(
                self.__configs_input.filepath
            )
        except ConfigsError as error:
            raise GearExecutionError(
                "Error reading pipeline configurations file"
                f"{self.__configs_input.filename}: {error}"
            ) from error

        # Load form configs for module configurations
        try:
            from pydantic import ValidationError
            from utils.utils import load_form_ingest_configurations

            form_project_configs = load_form_ingest_configurations(
                self.__form_configs_input.filepath
            )
        except ValidationError as error:
            raise GearExecutionError(
                f"Error reading form configurations file "
                f"{self.__form_configs_input.filename}: {error}"
            ) from error

        event_logger = VisitEventLogger(self.__event_bucket)

        # if source email specified, set up client to send emails
        email_client = (
            EmailClient(client=create_ses_client(), source=self.__source_email)
            if self.__source_email
            else None
        )

        run(
            proxy=self.proxy,
            project_id=project_id,
            pipeline_configs=pipeline_configs,
            event_logger=event_logger,
            module_configs=form_project_configs.module_configs,
            email_client=email_client,
            portal_url=self.__portal_url,
        )


def main():
    """Main method for FormSchedulerVisitor.

    Queues files for the submission pipeline.
    """

    GearEngine.create_with_parameter_store().run(gear_type=FormSchedulerVisitor)


if __name__ == "__main__":
    main()
