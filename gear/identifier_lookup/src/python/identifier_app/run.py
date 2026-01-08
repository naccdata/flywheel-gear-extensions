"""Entrypoint script for the identifier lookup app."""

import logging
import os
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List, Literal, Optional, TextIO

from configs.ingest_configs import ModuleConfigs
from error_logging.error_logger import ErrorLogTemplate
from error_logging.qc_status_log_creator import (
    FileVisitAnnotator,
    QCStatusLogManager,
)
from error_logging.qc_status_log_csv_visitor import QCStatusLogCSVVisitor
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logger import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
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
from identifiers.identifiers_lambda_repository import IdentifiersLambdaRepository
from identifiers.identifiers_repository import (
    IdentifierRepository,
)
from identifiers.model import IdentifiersMode
from inputs.center_validator import CenterValidator
from inputs.csv_reader import AggregateCSVVisitor, CSVVisitor, visit_all_strategy
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues
from lambdas.lambda_function import LambdaClient, create_lambda_client
from nacc_common.error_models import FileError
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from pydantic import ValidationError
from s3.s3_bucket import S3BucketInterface
from utils.utils import load_form_ingest_configurations

log = logging.getLogger(__name__)


class IdentifierLookupVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the identifier lookup app."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        identifiers_mode: IdentifiersMode,
        direction: Literal["nacc", "center"],
        gear_name: str,
        preserve_case: bool,
        config_input: Optional[InputFileWrapper] = None,
        event_logger: Optional[VisitEventLogger] = None,
        module: Optional[str] = None,
        single_center: bool = True,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__identifiers_mode: IdentifiersMode = identifiers_mode
        self.__direction: Literal["nacc", "center"] = direction
        self.__gear_name = gear_name
        self.__preserve_case = preserve_case
        self.__config_input = config_input
        self.__event_logger = event_logger
        self.__module = module
        self.__single_center = single_center

    @classmethod
    def create(
        cls, context: GearToolkitContext, parameter_store: Optional[ParameterStore]
    ) -> "IdentifierLookupVisitor":
        """Creates an identifier lookup execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Raises:
          GearExecutionError if rds parameter path is not set or S3 bucket is not
            accessible
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing input file"

        config_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )

        admin_id = context.config.get("admin_group", DefaultValues.NACC_GROUP_ID)
        mode = context.config.get("database_mode", "prod")
        direction = context.config.get("direction", "nacc")
        preserve_case = context.config.get("preserve_case", False)
        gear_name = context.manifest.get("name", "identifier-lookup")
        environment = context.config.get("environment", "prod")
        event_bucket = context.config.get("event_bucket", "nacc-event-logs")
        module = context.config.get("module")
        single_center = context.config.get("single_center", True)

        # Note: form_configs_file is optional for 'nacc' direction
        # When not provided, only basic identifier lookup will be performed

        # Initialize event logger for nacc direction with QC logging
        event_logger = None
        if direction == "nacc" and config_input is not None:
            try:
                s3_bucket = S3BucketInterface.create_from_environment(event_bucket)
                event_logger = VisitEventLogger(
                    s3_bucket=s3_bucket, environment=environment
                )
                log.info(
                    f"Event logging initialized for environment '{environment}' "
                    f"with bucket '{event_bucket}'"
                )
            except Exception as error:
                raise GearExecutionError(
                    f"Failed to initialize event logging: Unable to access S3 bucket "
                    f"'{event_bucket}'. Error: {error}"
                ) from error

        return IdentifierLookupVisitor(
            client=client,
            gear_name=gear_name,
            admin_id=admin_id,
            file_input=file_input,
            identifiers_mode=mode,
            direction=direction,
            preserve_case=preserve_case,
            config_input=config_input,
            event_logger=event_logger,
            module=module,
            single_center=single_center,
        )

    def __build_naccid_lookup(
        self,
        *,
        file_input: InputFileWrapper,
        identifiers_repo: IdentifierRepository,
        output_file: TextIO,
        error_writer: ListErrorWriter,
        misc_errors: List[FileError],
        timestamp: datetime,
    ) -> CSVVisitor:
        # Determine module name using the new logic
        module_configs: Optional[ModuleConfigs] = None
        module = self._determine_module()
        module_name = module.lower()

        if self.__config_input:
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

            module_configs = form_project_configs.module_configs.get(module)

        center_validator = None
        if module_configs and self.__single_center:
            # Get basic project information
            parent_project = file_input.get_parent_project(self.proxy)
            project = ProjectAdaptor(project=parent_project, proxy=self.proxy)

            try:
                adcid = project.get_pipeline_adcid()
            except (ProjectError, TypeError) as error:
                raise GearExecutionError(error) from error

            center_validator = CenterValidator(
                center_id=adcid,
                date_field=module_configs.date_field,
                error_writer=error_writer,
            )

        # Create identifier lookup visitor (always needed)
        # Ensure essential fields are always included
        essential_fields = [FieldNames.ADCID, FieldNames.PTID]
        if module_configs and module_configs.required_fields:
            # Combine module required fields with essential fields, avoiding duplicates
            required_fields = list(
                set(essential_fields + module_configs.required_fields)
            )
        else:
            required_fields = essential_fields
        naccid_visitor = NACCIDLookupVisitor(
            identifiers_repo=identifiers_repo,
            output_file=output_file,
            module_name=module_name,
            required_fields=required_fields,
            error_writer=error_writer,
            misc_errors=misc_errors,
            validator=center_validator,
        )

        # Start with just the identifier lookup visitor
        visitors: List[CSVVisitor] = [naccid_visitor]

        # Add QC status log visitor if we have module configs
        if module_configs:
            error_log_template = ErrorLogTemplate()
            visit_annotator = FileVisitAnnotator(project=project)
            qc_log_manager = QCStatusLogManager(
                error_log_template=error_log_template, visit_annotator=visit_annotator
            )

            qc_visitor = QCStatusLogCSVVisitor(
                module_configs=module_configs,
                project=project,
                qc_log_creator=qc_log_manager,
                gear_name=self.__gear_name,
                error_writer=error_writer,
                module_name=module_name,
            )
            visitors.append(qc_visitor)

        # Add event logging visitor if we have both event logger and module configs
        if self.__event_logger and module_configs:
            # Extract center label and project label from project adaptor
            center_label = project.group  # Use group as center label
            project_label = project.label

            event_visitor = CSVLoggingVisitor(
                center_label=center_label,
                project_label=project_label,
                gear_name=self.__gear_name,
                event_logger=self.__event_logger,
                module_configs=module_configs,
                error_writer=error_writer,
                timestamp=timestamp,
                action="submit",
                datatype="form",
            )
            visitors.append(event_visitor)

        # Combine visitors based on what's available
        return AggregateCSVVisitor(
            visitors=visitors, strategy_builder=visit_all_strategy
        )

    def _determine_module(self) -> str:
        """Determines the module name using filename suffix and/or config.

        Returns:
            The module name in uppercase

        Raises:
            GearExecutionError if no module can be determined or if there's a mismatch
        """
        # 1. Try to get module from filename suffix
        filename_module = self.__file_input.get_module_name_from_file_suffix()

        # 2. Get module from config if provided
        config_module = self.__module

        # 3. Determine final module based on priority and validation
        if config_module:
            # If config module is provided, use it
            if filename_module and filename_module.upper() != config_module.upper():
                raise GearExecutionError(
                    f"Module mismatch: filename suggests '{filename_module}' but "
                    f"config specifies '{config_module}'"
                )
            return config_module.upper()
        elif filename_module:
            # If no config module but filename has suffix, use filename
            return filename_module.upper()
        else:
            # No module identified from either source
            raise GearExecutionError(
                f"No module identified: filename '{self.__file_input.filename}' has no "
                f"module suffix and no module specified in config"
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
                # Extract file creation timestamp for event logging
                file_entry = self.__file_input.file_entry(context)
                timestamp = file_entry.created

                lookup_visitor = self.__build_naccid_lookup(
                    file_input=self.__file_input,
                    identifiers_repo=identifiers_repo,
                    output_file=out_file,
                    error_writer=error_writer,
                    misc_errors=misc_errors,
                    timestamp=timestamp,
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
                data=error_writer.errors().model_dump(by_alias=True),
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
