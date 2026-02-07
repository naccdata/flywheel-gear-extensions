"""Entry script for Identifier Provisioning."""

import logging
from pathlib import Path
from typing import Optional

from enrollment.enrollment_project import EnrollmentProject
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
    get_submitter,
)
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
)
from identifiers.model import IdentifiersMode
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from outputs.error_writer import ListErrorWriter

from identifier_provisioning_app.main import run

log = logging.getLogger(__name__)


class IdentifierProvisioningVisitor(GearExecutionEnvironment):
    """Execution visitor for NACCID provisioning gear."""

    # pylint: disable=(too-many-arguments)
    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        identifiers_mode: IdentifiersMode,
    ) -> None:
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__identifiers_mode: IdentifiersMode = identifiers_mode

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore]
    ) -> "IdentifierProvisioningVisitor":
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing expected input"

        options = context.config.opts
        return IdentifierProvisioningVisitor(
            client=client,
            admin_id=options.get("admin_group", DefaultValues.NACC_GROUP_ID),
            file_input=file_input,
            identifiers_mode=options.get("database_mode", "prod"),
        )

    def run(self, context: GearContext) -> None:
        """Runs the identifier provisioning app.

        Args:
          context: the gear execution context
        """

        assert context, "Gear context required"

        file_suffix = self.__file_input.get_module_name_from_file_suffix()
        enroll_module: str = context.config.opts.get(
            "enrollment_module", DefaultValues.ENROLLMENT_MODULE
        ).lower()
        if not file_suffix or file_suffix.lower() != enroll_module:
            raise GearExecutionError(
                f"Input file name {self.__file_input.filename} "
                f"expected to have {enroll_module} suffix."
            )

        if self.__file_input.has_qc_errors(gear_name=DefaultValues.QC_GEAR):
            log.error("input file %s has QC errors", self.__file_input.filename)
            return

        parent_project = self.__file_input.get_parent_project(self.proxy)
        project = ProjectAdaptor(project=parent_project, proxy=self.proxy)
        try:
            adcid = project.get_pipeline_adcid()
        except ProjectError as error:
            raise GearExecutionError(error) from error

        enrollment_project = EnrollmentProject.create_from(project)
        if not enrollment_project:
            raise GearExecutionError(
                f"Unable to get project containing file: {project.label}"
            )

        file = self.__file_input.file_entry(context)
        submitter = get_submitter(file=file, proxy=self.proxy)

        input_path = Path(self.__file_input.filepath)
        gear_name = self.gear_name(context, "identifier-provisioning")

        error_writer = ListErrorWriter(
            container_id=self.__file_input.file_id,
            fw_path=self.proxy.get_lookup_path(file),
        )

        sender_email = context.config.opts.get("sender_email", "nacc_dev@uw.edu")
        target_emails = context.config.opts.get("target_emails", "nacchelp@uw.edu")
        target_emails = [x.strip() for x in target_emails.split(",")]

        with open(input_path, mode="r", encoding="utf-8-sig") as csv_file:
            success = run(
                input_file=csv_file,
                center_id=adcid,
                error_writer=error_writer,
                enrollment_project=enrollment_project,
                gear_name=gear_name,
                repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode,
                ),
                submitter=submitter,
                sender_email=sender_email,
                target_emails=target_emails,
            )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors().model_dump(by_alias=True),
            )

            context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)


def main():
    """Main method for Identifier Provisioning."""

    GearEngine.create_with_parameter_store().run(
        gear_type=IdentifierProvisioningVisitor
    )


if __name__ == "__main__":
    main()
