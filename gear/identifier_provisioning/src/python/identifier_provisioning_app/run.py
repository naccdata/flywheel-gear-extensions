"""Entry script for Identifier Provisioning."""

import logging
from pathlib import Path
from typing import Optional

from enrollment.enrollment_project import EnrollmentProject
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (ClientWrapper, GearBotClient,
                                           GearEngine,
                                           GearExecutionEnvironment,
                                           GearExecutionError,
                                           InputFileWrapper)
from identifier_provisioning_app.main import run
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository, IdentifiersMode)
from inputs.parameter_store import ParameterStore
from lambdas.lambda_function import LambdaClient, create_lambda_client
from outputs.errors import ListErrorWriter

log = logging.getLogger(__name__)


class IdentifierProvisioningVisitor(GearExecutionEnvironment):
    """Execution visitor for NACCID provisioning gear."""

    # pylint: disable=(too-many-arguments)
    def __init__(self, client: ClientWrapper, admin_id: str,
                 file_input: InputFileWrapper,
                 identifiers_mode: IdentifiersMode) -> None:
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__identifiers_mode: IdentifiersMode = identifiers_mode

    @classmethod
    def create(
        cls, context: GearToolkitContext,
        parameter_store: Optional[ParameterStore]
    ) -> 'IdentifierProvisioningVisitor':
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name='input_file',
                                             context=context)
        admin_id = context.config.get("admin_group", "nacc")
        mode = context.config.get("identifiers_mode", "dev")

        return IdentifierProvisioningVisitor(client=client,
                                             admin_id=admin_id,
                                             file_input=file_input,
                                             identifiers_mode=mode)

    def run(self, context: GearToolkitContext) -> None:
        """Runs the identifier provisioning app.

        Args:
          context: the gear execution context
        """

        assert context, 'Gear context required'
        if self.__file_input.has_qc_errors():
            log.error('input file %s has QC errors',
                      self.__file_input.filename)
            return

        file_id = self.__file_input.file_id
        group_id = self.proxy.get_file_group(file_id)
        admin_group = self.admin_group(admin_id=self.__admin_id)
        adcid = admin_group.get_adcid(group_id)
        if adcid is None:
            raise GearExecutionError(
                f'Group {group_id} does not have an ADCID')

        file = self.proxy.get_file(file_id)
        file_group = self.proxy.find_group(group_id=group_id)
        if not file_group:
            raise GearExecutionError(
                f'Unable to get center group: {file.parents.group}')

        project = file_group.get_project_by_id(file.parents.project)
        if not project:
            raise GearExecutionError(
                f'Unable to get parent project: {file.parents.project}')
        enrollment_project = EnrollmentProject.create_from(project)
        if not enrollment_project:
            raise GearExecutionError('Unable to get project containing file: '
                                     f'{file.parents.project}')

        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode='r', encoding='utf-8') as csv_file:
            error_writer = ListErrorWriter(
                container_id=file_id, fw_path=self.proxy.get_lookup_path(file))
            success = run(
                input_file=csv_file,
                center_id=adcid,
                error_writer=error_writer,
                enrollment_project=enrollment_project,
                repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode))

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name="validation",
                                           state="PASS" if success else "FAIL",
                                           data=error_writer.errors())


def main():
    """Main method for Identifier Provisioning."""

    GearEngine.create_with_parameter_store().run(
        gear_type=IdentifierProvisioningVisitor)


if __name__ == "__main__":
    main()
