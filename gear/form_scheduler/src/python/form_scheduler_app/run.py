"""Entry script for form_scheduler."""
import logging
from typing import Any, Optional

from configs.ingest_configs import PipelineConfigs
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
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
from pydantic import ValidationError

from form_scheduler_app.main import run

log = logging.getLogger(__name__)


def load_form_pipeline_configurations(
        config_file_path: str) -> PipelineConfigs:
    """Load the form pipeline configs from the pipeline configs file.

    Args:
      config_file_path: the form module configs file path

    Returns:
      PipelineConfigs

    Raises:
      ValidationError if failed to load the configs file
    """

    with open(config_file_path, mode='r',
              encoding='utf-8-sig') as configs_file:
        return PipelineConfigs.model_validate_json(configs_file.read())


def is_another_gear_instance_running(proxy: FlywheelProxy, gear_name: str,
                                     project_id: str,
                                     current_job: str) -> bool:
    """Find whether another instance of the specified gear is running
    Args:
        proxy: the proxy for the Flywheel instance
        gear_name: gear name to check
        project_id: FLywheel project to check
        current_job: current job id

    Returns:
        bool: True if another job found, else False
    """
    search_str = JobPoll.generate_search_string(
        project_ids_list=[project_id],
        gears_list=[gear_name],
        states_list=['running', 'pending'])

    matched_jobs = proxy.find_jobs(search_str)
    if len(matched_jobs) > 1:
        return True

    return (current_job != matched_jobs[0].id)


class FormSchedulerVisitor(GearExecutionEnvironment):
    """Visitor for the Form Scheduler gear."""

    def __init__(self,
                 client: ClientWrapper,
                 pipeline_configs_input: InputFileWrapper,
                 source_email: Optional[str] = None,
                 portal_url: Optional[URLParameter] = None):
        super().__init__(client=client)

        self.__configs_input = pipeline_configs_input
        self.__source_email = source_email
        self.__portal_url = portal_url

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'FormSchedulerVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        pipeline_configs_input = InputFileWrapper.create(
            input_name='pipeline_configs_file', context=context)
        assert pipeline_configs_input, "missing expected input, pipeline_configs_file"

        source_email = context.config.get('source_email', 'nacchelp@uw.edu')

        portal_url = None
        if source_email:
            try:
                portal_path = context.config.get('portal_url_path', None)
                if not portal_path:
                    raise GearExecutionError("No portal URL found, required " +
                                             "to send emails")
                portal_url = parameter_store.\
                    get_portal_url(portal_path)  # type: ignore
            except ParameterError as error:
                raise GearExecutionError(
                    f'Parameter error: {error}') from error

        return FormSchedulerVisitor(
            client=client,
            pipeline_configs_input=pipeline_configs_input,
            source_email=source_email,
            portal_url=portal_url)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the Form Scheduler app."""
        try:
            dest_container: Any = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error

        if dest_container.container_type != 'project':
            raise GearExecutionError(
                f"Unsupported container type {dest_container.container_type}, "
                f"this gear must be executed at project level")

        project_id = dest_container.id

        # check for other form-scheduler gear jobs running on this project
        # there shouldn't be any
        gear_name = context.manifest.get('name', 'form-scheduler')
        job_id = context.config_json.get('job', {}).get('id')
        if is_another_gear_instance_running(proxy=self.proxy,
                                            gear_name=gear_name,
                                            project_id=project_id,
                                            current_job=job_id):
            raise GearExecutionError(
                "Another Form Scheduler gear already running on this project")

        try:
            pipeline_configs = load_form_pipeline_configurations(
                self.__configs_input.filepath)
        except ValidationError as error:
            raise GearExecutionError(
                'Error reading pipeline configurations file'
                f'{self.__configs_input.filename}: {error}') from error

        # if source email specified, set up client to send emails
        email_client = EmailClient(client=create_ses_client(),
                                   source=self.__source_email) \
            if self.__source_email else None

        run(proxy=self.proxy,
            project_id=project_id,
            pipeline_configs=pipeline_configs,
            email_client=email_client,
            portal_url=self.__portal_url)


def main():
    """Main method for FormSchedulerVisitor.

    Queues files for the submission pipeline.
    """

    GearEngine.create_with_parameter_store().run(
        gear_type=FormSchedulerVisitor)


if __name__ == "__main__":
    main()
