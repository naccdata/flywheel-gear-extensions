"""Entrypoint script for the identifier lookup app."""

import logging
import os
from pathlib import Path
from typing import Dict, Optional

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
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
    IdentifiersMode,
)
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject
from inputs.parameter_store import ParameterStore
from keys.keys import FieldNames
from lambdas.lambda_function import LambdaClient, create_lambda_client
from outputs.errors import ListErrorWriter

from identifier_app.main import run

log = logging.getLogger(__name__)


def get_identifiers(
    identifiers_repo: IdentifierRepository, adcid: int
) -> Dict[str, IdentifierObject]:
    """Gets all of the Identifier objects from the identifier database using
    the RDSParameters.

    Args:
      rds_parameters: the credentials for RDS MySQL with identifiers database
      adcid: the center ID
    Returns:
      the dictionary mapping from PTID to Identifier object
    """
    identifiers = {}
    center_identifiers = identifiers_repo.list(adcid=adcid)
    if center_identifiers:
        # pylint: disable=(not-an-iterable)
        identifiers = {
            identifier.ptid: identifier for identifier in center_identifiers}

    return identifiers


class IdentifierLookupVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the identifier lookup app."""

    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        identifiers_mode: IdentifiersMode,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__identifiers_mode: IdentifiersMode = identifiers_mode

    @classmethod
    def create(
        cls, context: GearToolkitContext, parameter_store: Optional[ParameterStore]
    ) -> "IdentifierLookupVisitor":
        """Creates an identifier lookup execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Raises:
          GearExecutionError if rds parameter path is not set
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(
            context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(
            input_name="input_file", context=context)
        assert file_input, "create raises exception if missing expected input"

        admin_id = context.config.get("admin_group", "nacc")
        mode = context.config.get("database_mode", "prod")

        return IdentifierLookupVisitor(
            client=client,
            admin_id=admin_id,
            file_input=file_input,
            identifiers_mode=mode,
        )

    def run(self, context: GearToolkitContext):
        """Runs the identifier lookup app.

        Args:
            context: the gear execution context
        """

        assert context, "Gear context required"

        file_id = self.__file_input.file_id
        admin_group = self.admin_group(admin_id=self.__admin_id)
        adcid = admin_group.get_adcid(self.proxy.get_file_group(file_id))
        if adcid is None:
            raise GearExecutionError("Unable to determine center ID for file")

        try:
            file = self.proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        project = self.proxy.get_project_by_id(file.parents.project)
        if not project:
            raise GearExecutionError(
                f"Failed to find the project with ID {file.parents.project}"
            )

        try:
            identifiers = get_identifiers(
                identifiers_repo=IdentifiersLambdaRepository(
                    client=LambdaClient(client=create_lambda_client()),
                    mode=self.__identifiers_mode,
                ),
                adcid=adcid,
            )
        except IdentifierRepositoryError as error:
            raise GearExecutionError(error) from error

        if not identifiers:
            raise GearExecutionError("Unable to load center participant IDs")

        module_name = self.__file_input.get_module_name_from_file_suffix()
        if not module_name:
            raise GearExecutionError(
                "Expect module suffix to input file name: "
                f"{self.__file_input.filename}"
            )

        date_field = (context.config.get(
            "date_field", FieldNames.DATE_COLUMN)).lower()

        gear_name = context.manifest.get("name", "identifier-lookup")

        (basename, extension) = os.path.splitext(self.__file_input.filename)
        filename = f"{basename}-identifier{extension}"
        input_path = Path(self.__file_input.filepath)
        with (
            open(input_path, mode="r", encoding="utf-8") as csv_file,
            context.open_output(filename, mode="w", encoding="utf-8") as out_file,
        ):
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(
                    self.proxy.get_file(file_id)),
            )
            success = run(
                input_file=csv_file,
                identifiers=identifiers,
                module_name=module_name,
                adcid=adcid,
                output_file=out_file,
                error_writer=error_writer,
                date_field=date_field,
                project=ProjectAdaptor(project=project, proxy=self.proxy),
                gear_name=gear_name,
            )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors(),
            )

            context.metadata.add_file_tags(
                self.__file_input.file_input, tags=gear_name)


def main():
    """The Identifiers Lookup gear reads a CSV file with rows for participants
    at a single ADRC, and having a PTID for the participant. The gear looks up
    the corresponding NACCID, and creates a new CSV file with the same
    contents, but with a new column for NACCID.

    Writes errors to a CSV file compatible with Flywheel error UI.
    """

    GearEngine.create_with_parameter_store().run(gear_type=IdentifierLookupVisitor)


if __name__ == "__main__":
    main()
