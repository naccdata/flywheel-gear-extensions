"""Entry script for Legacy Sanity Check."""

import logging
from typing import List, Optional

from configs.ingest_configs import FormProjectConfigs
from datastore.forms_store import FormsStore
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
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
from outputs.errors import ListErrorWriter
from pydantic import ValidationError

from legacy_sanity_check_app.main import LegacySanityChecker

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR)


class LegacySanityCheckVisitor(GearExecutionEnvironment):
    """Visitor for the Legacy Sanity Check gear."""

    def __init__(self, client: ClientWrapper, file_input: InputFileWrapper,
                 form_configs_input: InputFileWrapper,
                 ingest_project_label: str, sender_email: str,
                 target_emails: List[str]):
        super().__init__(client=client)

        self.__file_input = file_input
        self.__form_configs_input = form_configs_input
        self.__ingest_project_label = ingest_project_label
        self.__sender_email = sender_email
        self.__target_emails = target_emails

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'LegacySanityCheckVisitor':
        """Creates a Legacy Sanity Check execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        assert file_input, "missing expected input, input_file"

        form_configs_input = InputFileWrapper.create(
            input_name='form_configs_file', context=context)
        assert form_configs_input, "missing expected input, form_configs_file"

        config = context.config
        ingest_project_label = config.get('ingest_project_label',
                                          'ingest-form')
        sender_email = config.get('sender_email', 'no-reply@naccdata.org')
        target_emails = config.get('target_emails', 'nacchelp@uw.edu')
        target_emails = [x.strip() for x in target_emails.split(',')]

        return LegacySanityCheckVisitor(
            client=client,
            file_input=file_input,
            form_configs_input=form_configs_input,
            ingest_project_label=ingest_project_label,
            sender_email=sender_email,
            target_emails=target_emails)

    def run(self, context: GearToolkitContext) -> None:
        """Run the Legacy Sanity Checker."""
        file_id = self.__file_input.file_id
        try:
            file = self.proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        error_writer = ListErrorWriter(
            container_id=file_id, fw_path=self.proxy.get_lookup_path(file))

        form_configs = None
        with open(self.__form_configs_input.filepath, mode='r') as fh:
            form_configs = None
            try:
                form_configs = FormProjectConfigs.model_validate_json(
                    fh.read())
            except ValidationError as error:
                raise GearExecutionError(
                    'Error reading form configurations file'
                    f'{self.__form_configs_input.filename}: {error}'
                ) from error

        p_project = self.__file_input.get_parent_project(self.proxy, file=file)
        project = ProjectAdaptor(project=p_project, proxy=self.proxy)

        # grab the corresponding ingest (e.g. UDSv4) project based on the group
        ingest_project = None
        group = self.proxy.find_group(project.group)
        if group:
            ingest_project = group.find_project(
                label=self.__ingest_project_label)

        # all centers should have a corresponding ingest project
        # raise error if group/project not found - could also send email here?
        if not ingest_project:
            raise GearExecutionError(
                f"Could not find {self.__ingest_project_label} project "
                f"for {project.group}")

        sanity_checker = LegacySanityChecker(form_store=FormsStore(
            ingest_project=ingest_project, legacy_project=project),
                                             form_configs=form_configs,
                                             error_writer=error_writer,
                                             legacy_project=project)

        # could technically iterate on all subjects, but we only
        # really need to check the subject that had a new form.
        # could probably not even bother iterating on all modules
        subject = project.get_subject_by_id(
            file.parents.subject)  # type: ignore
        if not subject:
            raise GearExecutionError("Input file has no parent subject")

        if not sanity_checker.run_all_checks(subject.label):  # type: ignore
            sanity_checker.send_email(sender_email=self.__sender_email,
                                      target_emails=self.__target_emails,
                                      group_lbl=group.label)  # type: ignore


def main():
    """Main method for Legacy Sanity Check."""

    GearEngine.create_with_parameter_store().run(
        gear_type=LegacySanityCheckVisitor)


if __name__ == "__main__":
    main()
