"""Entry script for form_scheduler."""
import logging
from typing import Any, List, Optional

from flywheel.rest import ApiException
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import (
    ParameterError,
    ParameterStore,
    URLParameter,
)
from notifications.email import EmailClient, create_ses_client
from utils.utils import parse_string_to_list

from form_scheduler_app.main import FormSchedulerQueue, run

log = logging.getLogger(__name__)


class FormSchedulerVisitor(GearExecutionEnvironment):
    """Visitor for the Form Scheduler gear."""

    def __init__(self,
                 client: ClientWrapper,
                 queue_tags: List[str],
                 submission_pipeline: List[str],
                 module_order: List[str],
                 source_email: Optional[str] = None,
                 portal_url: Optional[URLParameter] = None):
        super().__init__(client=client)

        self.__submission_pipeline = submission_pipeline
        self.__module_order = module_order
        self.__queue_tags = queue_tags
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

        submission_pipeline = parse_string_to_list(
            context.config.get('submission_pipeline', None))
        accepted_modules = parse_string_to_list(
            context.config.get('accepted_modules', None))
        queue_tags = parse_string_to_list(context.config.get(
            'queue_tags', None),
                                          to_lower=False)
        source_email = context.config.get('source_email', None)

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

        if not submission_pipeline:
            raise GearExecutionError("No submission pipeline provided")
        if not accepted_modules:
            raise GearExecutionError("No accepted modules provided")
        if not queue_tags:
            raise GearExecutionError("No queue tags to search for provided")

        if submission_pipeline[0] != 'file-validator':
            raise GearExecutionError(
                "First gear in submission pipeline must be " +
                "the file validator")

        return FormSchedulerVisitor(client=client,
                                    submission_pipeline=submission_pipeline,
                                    module_order=accepted_modules,
                                    queue_tags=queue_tags,
                                    source_email=source_email,
                                    portal_url=portal_url)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the Form Scheduler app."""
        try:
            dest_container: Any = context.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f'Cannot find destination container: {error}') from error

        if not dest_container.container_type == 'project':
            raise GearExecutionError("Destination container must be a project")

        # if source email specified, set up client to send emails
        email_client = EmailClient(client=create_ses_client(),
                                   source=self.__source_email) \
            if self.__source_email else None

        queue = FormSchedulerQueue(proxy=self.proxy,
                                   module_order=self.__module_order,
                                   queue_tags=self.__queue_tags)

        run(proxy=self.proxy,
            queue=queue,
            project_id=dest_container.id,
            submission_pipeline=self.__submission_pipeline,
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
