"""Form ingest configurations."""

from json.decoder import JSONDecodeError
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Literal, Optional

from dates.form_dates import DEFAULT_DATE_FORMAT, convert_date
from error_logging.error_logger import ErrorLogTemplate
from flywheel.models.file_entry import FileEntry
from gear_execution.gear_trigger import GearInfo
from keys.keys import DefaultValues, PreprocessingChecks
from nacc_common.field_names import FieldNames
from pydantic import (
    BaseModel,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)

PipelineType = Literal["submission", "finalization"]


class ConfigsError(Exception):
    pass


class LabelTemplate(BaseModel):
    """Defines a string template object for generating labels using input data
    from file records."""

    template: str
    transform: Optional[Literal["upper", "lower"]] = Field(default=None)
    delimiter: Optional[str] = Field(default=None)

    def instantiate(
        self, record: Dict[str, Any], *, environment: Optional[Dict[str, Any]] = None
    ) -> str:
        """Instantiates the template using the data from the record matching
        the variables in the template. Converts the generated label to upper or
        lower case if indicated for the template.

        Args:
          record: data record
          env: environment variable settings
        Returns:
          the result of substituting values from the record.
        Raises:
          ValueError if a variable in the template does not occur in the record
        """
        result = self.template
        try:
            result = Template(self.template).substitute(record)
        except KeyError as error:
            if not environment:
                raise ValueError(
                    f"Error creating label, missing column {error}"
                ) from error

        if environment:
            try:
                result = Template(result).substitute(environment)
            except KeyError as error:
                raise ValueError(
                    f"Error creating label, missing column {error}"
                ) from error

        if self.delimiter:
            result = result.replace(" ", self.delimiter)

        if self.transform == "lower":
            return result.lower()

        if self.transform == "upper":
            # for filenames need to be careful about not
            # upper-casing the extension; can use pathlib
            # even if it's not actually a file
            file = Path(result)
            return file.stem.upper() + file.suffix

        return result


class UploadTemplateInfo(BaseModel):
    """Defines model for label template input."""

    session: LabelTemplate
    acquisition: LabelTemplate
    filename: LabelTemplate


class OptionalFormsConfigs(RootModel):
    root: Dict[str, Dict[str, List[str]]]

    def get_optional_forms(self, version: str, packet: str) -> Optional[List[str]]:
        """Get the list of optional forms for the specified version and packet.

        Args:
            version: form version
            packet: packet code

        Returns:
            Optional[List[str]]: List of optional form names if found
        """
        if not self.root:
            return None

        version_configs = self.root.get(version, {})
        return version_configs.get(packet)


class VisitLabelTemplate(BaseModel):
    """Template for creating a visit label for a data record."""

    id_field: str = FieldNames.PTID
    date_field: str = FieldNames.DATE_COLUMN

    def instantiate(self, record: Dict[str, Any], module: str) -> Optional[str]:
        """Instantiates this using the values for the template fields and
        module to create a visit-label.

        Constructs the label as "<id-field>_<date-field>_<module>".

        Args:
          record: the data record
          module: the module name
        Returns:
          the visit-label if all fields exist. None, otherwise.
        """
        components = []
        ptid = record.get(self.id_field)
        if not ptid:
            return None

        cleaned_ptid = ptid.strip().lstrip("0")
        if not cleaned_ptid:
            return None

        visitdate = record.get(self.date_field)
        if not visitdate:
            return None

        normalized_date = convert_date(
            date_string=visitdate, date_format=DEFAULT_DATE_FORMAT
        )
        if not normalized_date:
            return None

        components.append(cleaned_ptid)
        components.append(normalized_date)
        components.append(module.lower())

        return "_".join(components)


class SupplementModuleConfigs(BaseModel):
    label: str
    date_field: str
    version: Optional[str] = None
    exact_match: Optional[bool] = True


class LegacyModuleConfigs(BaseModel):
    label: str
    date_field: str
    initial_packets: Optional[List[str]] = None
    followup_packets: Optional[List[str]] = None


class ModuleConfigs(BaseModel):
    initial_packets: List[str]
    followup_packets: List[str]
    versions: List[str]
    date_field: str
    hierarchy_labels: UploadTemplateInfo
    required_fields: List[str]
    legacy_module: Optional[LegacyModuleConfigs] = None
    supplement_module: Optional[SupplementModuleConfigs] = None
    optional_forms: Optional[OptionalFormsConfigs] = None
    preprocess_checks: Optional[List[str]] = None
    errorlog_template: Optional[ErrorLogTemplate] = None
    longitudinal: Optional[bool] = True

    @model_validator(mode="after")
    def validate_preprocess_checks(self) -> "ModuleConfigs":
        not_defined = []
        if self.preprocess_checks:
            for check in self.preprocess_checks:
                if not PreprocessingChecks.is_check_defined(check):
                    not_defined.append(check)

            if not_defined:
                raise ValueError(
                    f"Following pre-processing checks are not defined: {not_defined}"
                )

        return self


class FormProjectConfigs(BaseModel):
    primary_key: str
    accepted_modules: List[str]
    module_configs: Dict[str, ModuleConfigs]
    legacy_project_label: Optional[str] = None
    qc_gear: Optional[str] = DefaultValues.QC_GEAR
    legacy_qc_gear: Optional[str] = DefaultValues.LEGACY_QC_GEAR

    def get_module_dependencies(self, module: str) -> Optional[List[str]]:
        """Get the list of dependent modules for a given module.
        Note: only returns the dependent modules that has an exact match.

        Args:
            module: module label

        Returns:
            List[str](optional): list of dependent module labels if found
        """

        dependent_modules = []
        for module_label, config in self.module_configs.items():
            if (
                config.supplement_module
                and config.supplement_module.exact_match
                and config.supplement_module.label == module.upper()
            ):
                dependent_modules.append(module_label)

        return dependent_modules


class Pipeline(BaseModel):
    """Defines model for form scheduler pipeline."""

    name: PipelineType
    modules: List[str]
    tags: List[str]
    extensions: List[str]
    starting_gear: GearInfo
    notify_user: bool = False

    def file_match(self, file_entry: FileEntry) -> bool:
        """Indicates whether the file matches the tags and extensions for the
        pipeline.

        Args:
          file_entry: the file
        Returns:
          True if the file tags and extension matches. False, otherwise.
        """
        return set(self.tags).issubset(
            set(file_entry.tags)
        ) and file_entry.name.lower().endswith(tuple(self.extensions))


class PipelineConfigs(BaseModel):
    gears: List[str]
    pipelines: List[Pipeline]

    @classmethod
    def load_form_pipeline_configurations(
        cls, config_file_path: str
    ) -> "PipelineConfigs":
        """Load the form pipeline configs from the pipeline configs file.

        Args:
            config_file_path: the form module configs file path

        Returns:
            PipelineConfigs

        Raises:
            ConfigsError if failed to load the configs file
        """

        try:
            with open(config_file_path, mode="r", encoding="utf-8-sig") as configs_file:
                return PipelineConfigs.model_validate_json(configs_file.read())
        except (
            FileNotFoundError,
            JSONDecodeError,
            TypeError,
            ValidationError,
        ) as error:
            raise ConfigsError(error) from error


def load_form_ingest_configurations(config_file_path: str) -> FormProjectConfigs:
    """Load the form module configs from the configs file.

    Args:
      config_file_path: the form module configs file path

    Returns:
      FormProjectConfigs

    Raises:
      ValidationError if failed to load the configs file
    """

    with open(config_file_path, mode="r", encoding="utf-8-sig") as configs_file:
        return FormProjectConfigs.model_validate_json(configs_file.read())
