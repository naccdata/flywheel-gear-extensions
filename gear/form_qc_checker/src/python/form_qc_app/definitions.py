"""Module for downloading and parsing rule definition schemas."""

import json
import logging
from io import StringIO
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Mapping, Optional

import yaml
from configs.ingest_configs import ModuleConfigs
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from keys.keys import DefaultValues
from nacc_common.error_models import VisitKeys
from nacc_common.field_names import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import empty_field_error
from s3.s3_bucket import S3BucketInterface

log = logging.getLogger(__name__)


class DefinitionException(Exception):
    """Raised when an error occurs during loading rule definitions."""


class DefinitionsLoader:
    """Class to load the validation rules definitions as python objects."""

    def __init__(
        self,
        *,
        s3_client: S3BucketInterface,
        error_writer: ErrorWriter,
        module_configs: ModuleConfigs,
        project: ProjectAdaptor,
        strict: bool = True,
    ):
        """

        Args:
            s3_bucket (S3BucketReader): S3 bucket to load rule definitions
            error_writer: error writer object to output error metadata
            module_configs: form ingest configs for the module
            project: Flywheel project adaptor
            strict (optional): Validation mode, defaults to True
        """

        self.__s3_bucket = s3_client
        self.__error_writer = error_writer
        self.__module_configs = module_configs
        self.__project = project
        self.__strict = strict

    def __get_s3_prefix(
        self,
        *,
        module: str,
        data_record: Dict[str, Any],
    ) -> str:
        """Get the S3 path prefix to load the definitions.

        Args:
            module: module label
            data_record: data record

        Returns:
            str: S3 path prefix
        """

        s3_prefix = f"{DefaultValues.QC_JSON_DIR}/{module.upper()}"
        formver = str(float(data_record.get(FieldNames.FORMVER, 0.0)))
        s3_prefix = f"{s3_prefix}/{formver}"
        if data_record.get(FieldNames.PACKET, None):
            packet = str(data_record[FieldNames.PACKET]).upper()
            s3_prefix = f"{s3_prefix}/{packet}"

        return s3_prefix

    def __load_from_schema_json_file(self, module: str) -> Dict[str, Mapping]:
        """Load the supplement module schema from project level schema json
        file.

        Args:
            module: supplement module label

        Returns:
            Dict[str, Mapping]: supplement schema if found, else empty schema
        """
        schema_files = [
            f"{module.lower()}-schema.json",
            f"{module.lower()}-legacy-schema.json",
        ]

        schema = {}
        for file in schema_files:
            try:
                data = json.loads(self.__project.read_file(file))
                if "definitions" in data:
                    schema = data["definitions"]
                    break
            except (ApiException, JSONDecodeError) as error:
                log.info(f"Failed to read schema file {file}: {error}")

        return schema

    def __append_supplement_schema(
        self,
        *,
        schema: Dict[str, Mapping],
        supplement_module: str,
        supplement_schema: Dict[str, Mapping],
    ):
        """Append supplement schema to the given schema. Only assign the type
        and set nullable to True, any other rules defined in the supplement
        schema are skipped.

        Args:
            schema: schema for input visit data
            supplement_module: supplement module label
            supplement_schema: schema for supplement module visit data
        """

        supplement_schema = (
            supplement_schema
            if supplement_schema
            else self.__load_from_schema_json_file(module=supplement_module)
        )

        for field in supplement_schema:
            if field not in schema:
                schema[field] = {"nullable": True}

                datatype = supplement_schema[field].get("type")
                if datatype:
                    if isinstance(datatype, list):
                        datatype = datatype[0]

                    if datatype == "number":
                        datatype = "float"

                    schema[field]["type"] = datatype  # type: ignore

    def load_definition_schemas(
        self,
        *,
        input_data: Dict[str, Any],
        module: str,
        optional_forms: Optional[Dict[str, bool]] = None,
        skip_forms: Optional[List[str]] = None,
        supplement_data: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Mapping], Optional[Dict[str, Dict]]]:
        """Download QC rule definitions and error code mappings from S3 bucket.

        Args:
            input_data: input data record
            module: module name,
            optional_forms (optional): Submission status of each optional form
            skip_forms (optional): List of form names to skip
            supplement_data (optional): supplement data record

        Returns:
            rule definition schema, code mapping schema (optional)

        Raises:
            DefinitionException: if error occurred while loading schemas
        """

        s3_prefix = self.__get_s3_prefix(module=module, data_record=input_data)
        schema = self.download_definitions_from_s3(
            f"{s3_prefix}/rules/", optional_forms, skip_forms
        )
        try:
            codes_map: Optional[Dict[str, Dict]] = self.download_definitions_from_s3(
                f"{s3_prefix}/codes/", optional_forms, skip_forms
            )  # type: ignore
            # TODO - validate code mapping schema
        except DefinitionException as error:
            log.warning(error)
            codes_map = None

        if codes_map:
            diff_keys = set(schema.keys()) ^ (codes_map.keys())
            if diff_keys:
                raise DefinitionException(
                    "Rule definitions and codes definitions does not match, "
                    f"list of fields missing in one of the schemas: {diff_keys}"
                )

        # load supplement module schema if a supplement record provided
        # skip optional forms to ensure the type is preserved
        if supplement_data:
            supplement_module = supplement_data.get(FieldNames.MODULE)
            if supplement_module:
                supplement_s3_prefix = self.__get_s3_prefix(
                    module=supplement_module,
                    data_record=supplement_data,
                )
                supplement_schema = {}
                try:
                    supplement_schema = self.download_definitions_from_s3(
                        f"{supplement_s3_prefix}/rules/"
                    )
                except DefinitionException as error:
                    log.warning(error)

                self.__append_supplement_schema(
                    schema=schema,
                    supplement_module=supplement_module,
                    supplement_schema=supplement_schema,
                )

        return schema, codes_map

    def download_definitions_from_s3(  # noqa: C901
        self,
        prefix: str,
        optional_forms: Optional[Dict[str, bool]] = None,
        skip_forms: Optional[List[str]] = None,
    ) -> Dict[str, Mapping]:
        """Download rule definition files from a source S3 bucket and generate
        validation schema. For optional forms, there are two definition files
        in the S3 bucket. Load the appropriate definition depending on whether
        the form is submitted or not.

        Args:
            prefix: S3 path prefix
            optional_forms (optional): Submission status of each optional form
            skip_forms (optional): List of form names to skip

        Returns:
            dict[str, Mapping[str, object]: Schema object from rule definitions

        Raises:
            DefinitionException: If error occurred while loading rule definitions
        """

        full_schema: dict[str, Mapping] = {}

        # Handle missing / at end of prefix
        if not prefix.endswith("/"):
            prefix += "/"

        rule_defs = self.__s3_bucket.read_directory(prefix)
        if not rule_defs:
            message = (
                "Failed to load definitions from the S3 bucket: "
                f"{self.__s3_bucket.bucket_name}/{prefix}"
            )
            raise DefinitionException(message)

        parser_error = False
        for key, file_object in rule_defs.items():
            filename = key.removeprefix(prefix)
            formname = filename.partition("_")[0]

            if skip_forms and formname in skip_forms:
                log.info("Skipping definition file: %s", key)
                continue

            optional_def = filename.endswith("_optional.json")
            if optional_def and not optional_forms:
                continue  # skip optional form if no optional forms specified

            # Select which definition to load depending on form is submitted or not
            if optional_forms and formname in optional_forms:
                if optional_forms[formname] and optional_def:
                    continue  # form is submitted, skip optional schema

                if not optional_forms[formname] and not optional_def:
                    continue  # form not submitted, skip regular schema

            if "Body" not in file_object:
                log.error("Failed to load the definition file: %s", key)
                parser_error = True
                continue

            file_data = StringIO(file_object["Body"].read().decode("utf-8"))
            rules_type = "json"
            if "ContentType" in file_object:
                rules_type = file_object["ContentType"]

            try:
                if "json" in rules_type:
                    form_def = json.load(file_data)
                elif "yaml" in rules_type:
                    form_def = yaml.safe_load(file_data)
                else:
                    log.error(
                        "Unhandled definition file type: %s - %s", key, rules_type
                    )
                    parser_error = True
                    continue

                # If there are any duplicate keys(i.e. variable names) across
                # forms, they will be replaced with the latest definitions.
                # It is assumed all variable names are unique within a project
                if form_def:
                    full_schema.update(form_def)
                    log.info("Parsed definition file: %s", key)
                else:
                    log.error("Empty definition file: %s", key)
                    parser_error = True
            except (JSONDecodeError, yaml.YAMLError, TypeError) as error:
                log.error("Failed to parse the definition file: %s - %s", key, error)
                parser_error = True

        if parser_error:
            raise DefinitionException(
                "Error(s) occurred while loading definition schemas"
            )

        return full_schema

    def get_optional_forms_submission_status(
        self, *, input_data: Dict[str, Any], module: str
    ) -> Optional[Dict[str, bool]]:
        """Get the list of optional forms for the module/packet from
        optional_forms.json file in rule definitions S3 bucket. Check whether
        each optional form is submitted or not using the mode variable in input
        data.

        Args:
            input_data: input data record
            module: module name

        Returns:
            Dict[str, bool]: submission status of each optional form

        Raises:
            DefinitionException: If failed to get optional forms submission status
        """

        if not self.__module_configs.optional_forms:
            log.warning("Optional forms information not defined for module %s", module)
            return None

        formver = str(float(input_data.get(FieldNames.FORMVER, 0.0)))

        # some modules may not have separate packet codes, set to 'D' for default
        packet = input_data.get(FieldNames.PACKET, "D")

        optional_forms = self.__module_configs.optional_forms.get_optional_forms(
            version=formver, packet=packet
        )

        if not optional_forms:
            log.warning(
                "Optional forms information not available for %s/%s/%s",
                module,
                formver,
                packet,
            )
            return None

        missing = []
        submission_status = {}
        for form in optional_forms:
            mode_var = f"{FieldNames.MODE}{form.lower()}"
            mode = str(input_data.get(mode_var, ""))
            if not mode.strip():
                if self.__strict:
                    missing.append(mode_var)
                else:
                    submission_status[form] = False

                continue

            submission_status[form] = int(mode) != DefaultValues.NOTFILLED

        if missing:
            self.__error_writer.write(
                empty_field_error(
                    field=set(missing),
                    visit_keys=VisitKeys.create_from(
                        record=input_data, date_field=self.__module_configs.date_field
                    ),
                )
            )
            raise DefinitionException(
                f"Missing optional forms submission status fields {missing}"
            )

        return submission_status
