"""Entry script for Form QC Coordinator."""

import logging
from typing import Any, Optional

from configs.ingest_configs import (
    FormProjectConfigs,
    PipelineType,
    load_form_ingest_configurations,
)
from flywheel import Subject
from flywheel.rest import ApiException
from flywheel_adaptor.subject_adaptor import (
    ParticipantVisits,
    SubjectAdaptor,
    VisitInfo,
)
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from gear_execution.gear_trigger import GearInfo
from inputs.parameter_store import ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream
from keys.keys import DefaultValues, MetadataKeys
from nacc_common.field_names import FieldNames
from pydantic import ValidationError

from form_qc_coordinator_app.coordinator import QCGearConfigs
from form_qc_coordinator_app.main import run

log = logging.getLogger(__name__)


class FormQCCoordinator(GearExecutionEnvironment):
    """The gear execution visitor for the form-qc-coordinator."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        form_config_input: InputFileWrapper,
        qc_config_input: InputFileWrapper,
        subject_id: str,
        pipeline: PipelineType,
        check_all: bool = False,
    ):
        """
        Args:
            client: Flywheel SDK client wrapper
            file_input: Gear input file wrapper
            form_config_input: forms module configurations file
            qc_config_input: QC gear configurations file
            subject_id: Flywheel subject id
            pipeline: Pipeline that triggered this gear instance
            check_all: If True, re-evaluate all visits for the module/participant
        """
        self.__file_input = file_input
        self.__form_config_input = form_config_input
        self.__qc_config_input = qc_config_input
        self.__subject_id = subject_id
        self.__pipeline = pipeline
        self.__check_all = check_all
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "FormQCCoordinator":
        """Creates a gear execution object, loads gear context.

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

        try:
            dest_container: Any = context.config.get_destination_container()
        except ApiException as error:
            raise GearExecutionError(
                f"Cannot find destination container: {error}"
            ) from error

        if dest_container.container_type == "subject":
            subject_id = dest_container.id
        elif dest_container.container_type == "acquisition":
            subject_id = dest_container.parents["subject"]
        else:
            raise GearExecutionError(
                f"Unsupported container type {dest_container.container_type}"
            )

        visits_file_input = InputFileWrapper.create(
            input_name="visits_file", context=context
        )
        assert visits_file_input, "missing expected input, visits_file"

        form_configs_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )
        assert form_configs_input, "missing expected input, form_configs_file"

        qc_configs_input = InputFileWrapper.create(
            input_name="qc_configs_file", context=context
        )
        assert qc_configs_input, "missing expected input, qc_configs_file"

        options = context.config.opts

        return FormQCCoordinator(
            client=client,
            file_input=visits_file_input,
            form_config_input=form_configs_input,
            qc_config_input=qc_configs_input,
            subject_id=subject_id,
            pipeline=options.get("pipeline", "submission"),
            check_all=options.get("check_all", False),
        )

    def __parse_json_input(
        self, subject: SubjectAdaptor, form_configs: FormProjectConfigs
    ) -> Optional[ParticipantVisits]:
        """Parse the JSON input file and return visits info.

        Args:
            subject: Flywheel subject adaptor
            form_configs: form ingest configurations

        Raises:
            GearExecutionError: if error occurs while parsing the input

        Returns:
            ParticipantVisits(optional): visits info if input parsed successfully
        """

        module = self.__file_input.get_module_name_from_file_suffix(
            separator="_", allowed="a-z", split=None, extension="json"
        )
        if not module:
            raise GearExecutionError(
                "Failed to extract module information from file "
                f"{self.__file_input.filename}"
            )
        module = module.upper()

        file_id = self.__file_input.file_id
        try:
            file = self.proxy.get_file(file_id)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file {self.__file_input.filename}: {error}"
            ) from error

        module_configs = form_configs.module_configs.get(module)
        if not module_configs:
            raise GearExecutionError(
                f"Failed to find module configurations for {module} module"
            )

        visitdate = (
            file.info.get("forms", {}).get("json", {}).get(module_configs.date_field)
        )
        if not visitdate:
            raise GearExecutionError(
                f"{MetadataKeys.get_column_key(module_configs.date_field)} "
                f"not found in file {self.__file_input.filename} metadata"
            )

        visitnum = file.info.get("forms", {}).get("json", {}).get(FieldNames.VISITNUM)

        visit = VisitInfo(
            filename=self.__file_input.filename,
            file_id=file_id,
            visitdate=visitdate,
            visitnum=visitnum,
            validated_timestamp=file.info.get(MetadataKeys.VALIDATED_TIMESTAMP),
        )

        visits_info = ParticipantVisits(
            participant=subject.label, module=module, visits=[visit]
        )

        return visits_info

    def __parse_yaml_input(
        self, subject: SubjectAdaptor
    ) -> Optional[ParticipantVisits]:
        """Parse the YAML input file and return visits info.

        Args:
            subject: Flywheel subject adaptor

        Returns:
            ParticipantVisits(optional): visits info if input parsed successfully
        """

        try:
            with open(
                self.__file_input.filepath, "r", encoding="utf-8-sig "
            ) as input_file:
                input_data = load_from_stream(input_file)
        except (FileNotFoundError, YAMLReadError) as error:
            log.error(
                f"Failed to read the input file {self.__file_input.filename}: {error}"
            )
            return None

        try:
            visits_info = ParticipantVisits.model_validate(input_data)
        except ValidationError as error:
            log.error("Visit information not in expected format - %s", error)
            return None

        if visits_info and subject.label != visits_info.participant:
            log.error(
                f"Participant label in visits file {visits_info.participant} "
                f"does not match with subject label {subject.label}"
            )
            return None

        return visits_info

    def __validate_input_data(
        self, subject: SubjectAdaptor, form_configs: FormProjectConfigs
    ) -> Optional[ParticipantVisits]:
        """Validate the input file - visits_file.

        Args:
            input_file_path: Gear input 'visits_file' file path
            subject_lbl: Flywheel subject label

        Returns:
            Optional[ParticipantVisits]: Info on the set of new/updated visits
        """

        accepted_extensions = ["yaml", "json"]
        file_type = self.__file_input.validate_file_extension(
            accepted_extensions=accepted_extensions
        )
        if not file_type:
            raise GearExecutionError(
                f"Unsupported input file type {self.__file_input.file_type}, "
                f"supported extension(s): {accepted_extensions}"
            )

        if self.__pipeline == "submission" and file_type != "yaml":
            raise GearExecutionError(
                f"Unsupported input file type `{file_type}` for pipeline "
                f"`{self.__pipeline}` - expected yaml file"
            )

        if file_type == "json":
            return self.__parse_json_input(subject, form_configs=form_configs)

        return self.__parse_yaml_input(subject)

    def __update_input_file_tags(self, gear_context: GearContext):
        """Add gear tag to input file.

        Args:
            gear_context: Flywheel gear context
            input_wrapper: gear input file wrapper
        """
        gear_name = gear_context.manifest.name
        if not gear_name:
            gear_name = "form-qc-coordinator"

        gear_context.metadata.add_file_tags(
            self.__file_input.file_input, tags=gear_name
        )

    def run(self, context: GearContext) -> None:
        """Validates input files, runs the form-qc-coordinator app.

        Args:
            context: the gear execution context

        Raises:
          GearExecutionError
        """

        try:
            subject: Subject = self.proxy.get_container_by_id(self.__subject_id)  # type: ignore
        except ApiException as error:
            raise GearExecutionError(
                f"Cannot find subject with ID {self.__subject_id}: {error}"
            ) from error

        try:
            form_project_configs = load_form_ingest_configurations(
                self.__form_config_input.filepath
            )
        except ValidationError as error:
            raise GearExecutionError(
                "Error reading form configurations file "
                f"{self.__form_config_input.filename}: {error}"
            ) from error

        subject_adaptor = SubjectAdaptor(subject)
        visits_info = self.__validate_input_data(
            subject=subject_adaptor, form_configs=form_project_configs
        )
        if not visits_info:
            raise GearExecutionError(
                f"Error reading visits info file {self.__file_input.filename}"
            )

        qc_gear_info = GearInfo.load_from_file(
            self.__qc_config_input.filepath, configs_class=QCGearConfigs
        )
        if not qc_gear_info:
            raise GearExecutionError(
                f"Error reading qc gear configs file {self.__qc_config_input.filename}"
            )

        run(
            gear_context=context,
            proxy=self.proxy,
            form_project_configs=form_project_configs,
            configs_file=self.__form_config_input.file_entry(context=context),
            subject=subject_adaptor,
            visits_info=visits_info,
            qc_gear_info=qc_gear_info,
            pipeline=self.__pipeline,  # type: ignore
            check_all=self.__check_all,
        )

        if self.__pipeline == DefaultValues.SUBMISSION_PIPELINE:
            self.__update_input_file_tags(context)


def main():
    """Main method for Form QC Coordinator."""

    GearEngine.create_with_parameter_store().run(gear_type=FormQCCoordinator)


if __name__ == "__main__":
    main()
