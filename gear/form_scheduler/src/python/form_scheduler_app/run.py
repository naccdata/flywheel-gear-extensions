"""Entry script for form_scheduler."""

import logging
from typing import Any, Literal, Optional

from botocore.exceptions import ClientError
from configs.ingest_configs import ConfigsError, PipelineConfigs
from event_capture.event_capture import VisitEventCapture
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
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

from form_scheduler_app.form_scheduler_queue import (
    FormSchedulerError,
    FormSchedulerQueue,
)
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
        event_environment: Literal["prod", "dev"],
        source_email: Optional[str] = None,
        portal_url: Optional[URLParameter] = None,
    ):
        super().__init__(client=client)

        self.__configs_input = pipeline_configs_input
        self.__form_configs_input = form_configs_input
        self.__source_email = source_email
        self.__portal_url = portal_url
        self.__event_bucket = event_bucket
        self.__event_environment = event_environment

    @classmethod
    def create(
        cls,
        context: GearContext,
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

        options = context.config.opts
        source_email = options.get("source_email", "nacchelp@uw.edu")

        portal_url = None
        if source_email:
            try:
                portal_path = options.get("portal_url_path", None)
                if not portal_path:
                    raise GearExecutionError(
                        "No portal URL found, required " + "to send emails"
                    )
                portal_url = parameter_store.get_portal_url(portal_path)  # type: ignore
            except ParameterError as error:
                raise GearExecutionError(f"Parameter error: {error}") from error

        event_bucket_name = options.get("event_bucket", "submission-events")
        event_environment = options.get("event_environment", "prod")

        try:
            event_bucket = S3BucketInterface.create_from_environment(event_bucket_name)
        except ClientError as error:
            raise GearExecutionError(
                f"Failed to initialize S3 bucket interface: "
                f"Unable to access S3 bucket '{event_bucket_name}'. Error: {error}"
            ) from error

        return FormSchedulerVisitor(
            client=client,
            pipeline_configs_input=pipeline_configs_input,
            form_configs_input=form_configs_input,
            event_bucket=event_bucket,
            event_environment=event_environment,
            source_email=source_email,
            portal_url=portal_url,
        )

    def run(self, context: GearContext) -> None:
        """Runs the Form Scheduler app."""
        try:
            dest_container: Any = context.config.get_destination_container()
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
        gear_name = self.gear_name(context, "form-scheduler")
        job_id = context.config.job.get("id")

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

        event_logger = VisitEventCapture(
            s3_bucket=self.__event_bucket, environment=self.__event_environment
        )

        # if source email specified, set up client to send emails
        email_client = (
            EmailClient(client=create_ses_client(), source=self.__source_email)
            if self.__source_email
            else None
        )

        # Get the project
        fw_project = self.proxy.get_project_by_id(project_id)
        if not fw_project:
            raise GearExecutionError(f"Cannot find project with ID {project_id}")
        project = ProjectAdaptor(project=fw_project, proxy=self.proxy)

        # Create the queue
        queue = FormSchedulerQueue(
            proxy=self.proxy,
            project=project,
            pipeline_configs=pipeline_configs,
            event_capture=event_logger,
            email_client=email_client,
            portal_url=self.__portal_url,
        )

        try:
            run(queue=queue, pipeline_configs=pipeline_configs)
        except FormSchedulerError as error:
            raise GearExecutionError(error) from error


def main():
    """Main method for FormSchedulerVisitor.

    Queues files for the submission pipeline.
    """

    GearEngine.create_with_parameter_store().run(gear_type=FormSchedulerVisitor)


if __name__ == "__main__":
    main()
