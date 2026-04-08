"""Entry script for Form Deletion."""

import logging
from typing import Optional

from configs.ingest_configs import FormProjectConfigs, load_form_ingest_configurations
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
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
from pydantic import ValidationError
from submissions.models import DeleteRequest

from form_deletion_app.main import run

log = logging.getLogger(__name__)


class FormDeletionVisitor(GearExecutionEnvironment):
    """Visitor for the Delete Form Submission gear."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        request_file_input: InputFileWrapper,
        form_configs_input: InputFileWrapper,
    ):
        """
        Args:
            client: Flywheel SDK client wrapper
            request_file_input: Delete request file wrapper
            form_configs_input: Forms module configurations file wrapper
        """

        self.__request_file_input = request_file_input
        self.__form_configs_input = form_configs_input
        super().__init__(client=client)

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore] = None
    ) -> "FormDeletionVisitor":
        """Creates a Delete Form Submission execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        assert parameter_store, "Parameter store expected"
        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        delete_request_input = InputFileWrapper.create(
            input_name="request_file", context=context
        )
        assert delete_request_input, "missing expected input, request_file"

        form_configs_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )
        assert form_configs_input, "missing expected input, form_configs_file"

        return FormDeletionVisitor(
            client=client,
            request_file_input=delete_request_input,
            form_configs_input=form_configs_input,
        )

    def run(self, context: GearContext) -> None:
        try:
            with open(
                self.__request_file_input.filepath, mode="r", encoding="utf-8-sig"
            ) as delete_request_file:
                delete_request = DeleteRequest.model_validate_json(
                    delete_request_file.read()
                )
        except ValidationError as error:
            raise GearExecutionError(
                "Error reading delete request file "
                f"{self.__request_file_input.filename}: {error}"
            ) from error

        try:
            form_project_configs: FormProjectConfigs = load_form_ingest_configurations(
                self.__form_configs_input.filepath
            )
        except ValidationError as error:
            raise GearExecutionError(
                "Error reading form configurations file "
                f"{self.__form_configs_input.filename}: {error}"
            ) from error

        module = delete_request.module.upper()
        module_configs = form_project_configs.module_configs.get(module)
        if not module_configs:
            raise GearExecutionError(
                f"Failed to find the configurations for module {module}"
            )

        parent_project = self.__request_file_input.get_parent_project(self.proxy)
        project = ProjectAdaptor(project=parent_project, proxy=self.proxy)

        run(
            proxy=self.proxy,
            project=project,
            delete_request=delete_request,
            module_configs=module_configs,
        )


def main():
    """Main method for Delete Form Submission."""

    GearEngine().run(gear_type=FormDeletionVisitor)


if __name__ == "__main__":
    main()
