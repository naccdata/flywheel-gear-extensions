"""Entrypoint script for the identifier lookup app."""

import logging
import os
from io import StringIO
from pathlib import Path
from typing import Dict, List, Literal, Optional, TextIO

from configs.ingest_configs import ModuleConfigs
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
from identifier_app.main import CenterLookupVisitor, NACCIDLookupVisitor, run
from identifiers.identifiers_lambda_repository import (
    IdentifiersLambdaRepository,
    IdentifiersMode,
)
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject
from inputs.csv_reader import CSVVisitor
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from outputs.errors import FileError, ListErrorWriter
from pydantic import ValidationError
from utils.utils import load_form_ingest_configurations

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
        identifiers = {identifier.ptid: identifier for identifier in center_identifiers}

    return identifiers


class IdentifierLookupVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the identifier lookup app."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        config_input: InputFileWrapper,
        identifiers_mode: IdentifiersMode,
        direction: Literal["nacc", "center"],
        gear_name: str,
        preserve_case: bool,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__config_input = config_input
        self.__identifiers_mode: IdentifiersMode = identifiers_mode
        self.__direction: Literal["nacc", "center"] = direction
        self.__gear_name = gear_name
        self.__preserve_case = preserve_case

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

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing input file"

        config_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )
        assert config_input, "create raises exception if missing configuration file"

        admin_id = context.config.get("admin_group", DefaultValues.NACC_GROUP_ID)
        mode = context.config.get("database_mode", "prod")
        direction = context.config.get("direction", "nacc")
        preserve_case = context.config.get("preserve_case", False)
        gear_name = context.manifest.get("name", "identifier-lookup")

        return IdentifierLookupVisitor(
            client=client,
            gear_name=gear_name,
            admin_id=admin_id,
            file_input=file_input,
            config_input=config_input,
            identifiers_mode=mode,
            direction=direction,
            preserve_case=preserve_case,
        )

    def __build_naccid_lookup(
        self,
        *,
        file_input: InputFileWrapper,
        identifiers_repo: IdentifierRepository,
        output_file: TextIO,
        error_writer: ListErrorWriter,
        misc_errors: List[FileError],
    ) -> CSVVisitor:
        module = self.__file_input.get_module_name_from_file_suffix()
        if not module:
            raise GearExecutionError(
                "Expect module suffix in input file name: "
                f"{self.__file_input.filename}"
            )
        module = module.upper()

        try:
            form_project_configs = load_form_ingest_configurations(
                self.__config_input.filepath
            )
        except ValidationError as error:
            raise GearExecutionError(
                "Error reading form configurations file"
                f"{self.__config_input.filename}: {error}"
            ) from error

        if (
            module not in form_project_configs.accepted_modules
            or not form_project_configs.module_configs.get(module)
        ):
            raise GearExecutionError(
                f"Failed to find the configurations for module {module}"
            )

        module_configs: ModuleConfigs = form_project_configs.module_configs.get(module)  # type: ignore

        admin_group = self.admin_group(admin_id=self.__admin_id)
        adcid = admin_group.get_adcid(self.proxy.get_file_group(file_input.file_id))
        if adcid is None:
            raise GearExecutionError("Unable to determine center ID for file")

        project = file_input.get_parent_project(self.proxy)

        try:
            identifiers = get_identifiers(
                identifiers_repo=identifiers_repo, adcid=adcid
            )
        except IdentifierRepositoryError as error:
            raise GearExecutionError(error) from error

        if not identifiers:
            raise GearExecutionError("Unable to load center participant IDs")

        return NACCIDLookupVisitor(
            adcid=adcid,
            identifiers=identifiers,
            output_file=output_file,
            module_name=module.lower(),
            module_configs=module_configs,
            error_writer=error_writer,
            gear_name=self.__gear_name,
            project=ProjectAdaptor(project=project, proxy=self.proxy),
            misc_errors=misc_errors,
        )

    def __build_center_lookup(
        self,
        *,
        identifiers_repo: IdentifierRepository,
        output_file: TextIO,
        error_writer: ListErrorWriter,
    ) -> CSVVisitor:
        return CenterLookupVisitor(
            identifiers_repo=identifiers_repo,
            output_file=output_file,
            error_writer=error_writer,
        )

    def run(self, context: GearToolkitContext):
        """Runs the identifier lookup app.

        Args:
            context: the gear execution context
        """

        assert context, "Gear context required"

        identifiers_repo = IdentifiersLambdaRepository(
            client=LambdaClient(client=create_lambda_client()),
            mode=self.__identifiers_mode,
        )

        (basename, extension) = os.path.splitext(self.__file_input.filename)
        filename = f"{basename}_{DefaultValues.IDENTIFIER_SUFFIX}{extension}"
        input_path = Path(self.__file_input.filepath)
        out_file = StringIO()

        with open(input_path, mode="r", encoding="utf-8-sig") as csv_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )

            clear_errors = False
            misc_errors: List[FileError] = []
            if self.__direction == "nacc":
                lookup_visitor = self.__build_naccid_lookup(
                    file_input=self.__file_input,
                    identifiers_repo=identifiers_repo,
                    output_file=out_file,
                    error_writer=error_writer,
                    misc_errors=misc_errors,
                )
                clear_errors = True
            elif self.__direction == "center":
                lookup_visitor = self.__build_center_lookup(
                    identifiers_repo=identifiers_repo,
                    output_file=out_file,
                    error_writer=error_writer,
                )

            success = run(
                input_file=csv_file,
                lookup_visitor=lookup_visitor,
                error_writer=error_writer,
                clear_errors=clear_errors,
                preserve_case=self.__preserve_case,
            )

            contents = out_file.getvalue()
            if len(contents) > 0:
                log.info("Writing contents")
                with context.open_output(filename, mode="w", encoding="utf-8") as fh:
                    fh.write(contents)
            else:
                log.info("Contents empty, will not write output file")

            # If there are any miscellaneous errors that can't be reported for a visit
            # add those to CSV file errors
            if misc_errors:
                for error in misc_errors:
                    error_writer.write(error)

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors(),
            )

            context.metadata.add_file_tags(
                self.__file_input.file_input, tags=self.__gear_name
            )


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
