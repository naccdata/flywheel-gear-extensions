"""Entry script for Identifier Provisioning."""

import logging
from pathlib import Path
from typing import Optional

from enrollment.enrollment_project import EnrollmentProject
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
    IdentifiersMode,
)
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from outputs.errors import ListErrorWriter

from identifier_provisioning_app.main import run

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
        assert file_input, "create raises exception if missing expected input"

        admin_id = context.config.get("admin_group", "nacc")
        mode = context.config.get("database_mode", "prod")

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

        file_suffix = self.__file_input.get_module_name_from_file_suffix()
        enroll_module: str = context.config.get(
            "enrollment_module", DefaultValues.ENROLLMENT_MODULE).lower()
        if not file_suffix or not (
            (f'{enroll_module}_{file_suffix.lower()}'
             == f'{enroll_module}_{DefaultValues.PROV_SUFFIX}') or
            (file_suffix.lower() == enroll_module)):
            raise GearExecutionError(
                f'Input file name {self.__file_input.filename} '
                f'expected to have {enroll_module} suffix.')

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
        gear_name = context.manifest.get('name', 'identifier-provisioning')
        with open(input_path, mode='r', encoding='utf-8') as csv_file:
            error_writer = ListErrorWriter(
                container_id=file_id, fw_path=self.proxy.get_lookup_path(file))
            success = run(
                input_file=csv_file,
                center_id=adcid,
                error_writer=error_writer,
                enrollment_project=enrollment_project,
                gear_name=gear_name,
                repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode))

            context.metadata.add_qc_result(self.__file_input.file_input,
                                           name="validation",
                                           state="PASS" if success else "FAIL",
                                           data=error_writer.errors())

            context.metadata.add_file_tags(self.__file_input.file_input,
                                           tags=gear_name)


def main():
    """Main method for Identifier Provisioning."""

    GearEngine.create_with_parameter_store().run(
        gear_type=IdentifierProvisioningVisitor)


if __name__ == "__main__":
    main()
