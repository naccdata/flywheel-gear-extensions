"""Module for downloading and parsing rule definition schemas."""

import json
import logging
from io import StringIO
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Mapping, Optional

import yaml
from keys.keys import DefaultValues, FieldNames
from outputs.errors import ListErrorWriter, empty_field_error, system_error
from s3.s3_client import S3BucketReader

log = logging.getLogger(__name__)


class DefinitionException(Exception):
    """Raised when an error occurs during loading rule definitions."""


class DefinitionsLoader:
    """Class to load the validation rules definitions as python objects."""

    def __init__(self,
                 *,
                 s3_client: S3BucketReader,
                 error_writer: ListErrorWriter,
                 strict: bool = True):
        """

        Args:
            s3_bucket (S3BucketReader): S3 bucket to load rule definitions
            error_writer: error writer object to output error metadata
            strict (optional): Validation mode, defaults to True.
        """

        self.__s3_bucket = s3_client
        self.__error_writer = error_writer
        self.__strict = strict
        # optional forms file in S3 bucket
        self.__opfname = 'optional_forms.json'

    def load_definition_schemas(
        self,
        *,
        input_data: dict[str, Any],
        module: str,
        optional_forms: Optional[Dict[str, bool]] = None
    ) -> tuple[Dict[str, Mapping], Optional[Dict[str, Dict]]]:
        """Download QC rule definitions and error code mappings from S3 bucket.

        Args:
            input_data: input data record
            module: module name,
            optional_forms(optional): Submission status of each optional form

        Returns:
            rule definition schema, code mapping schema (optional)

        Raises:
            DefinitionException: if error occurred while loading schemas
        """

        s3_prefix = module
        if input_data.get(FieldNames.FORMVER, None):
            formver = str(input_data[FieldNames.FORMVER])
            s3_prefix = f'{s3_prefix}/{formver}'

        if input_data.get(FieldNames.PACKET, None):
            packet = str(input_data[FieldNames.PACKET]).upper()
            s3_prefix = f'{s3_prefix}/{packet}'

        schema = self.download_definitions_from_s3(f'{s3_prefix}/rules/',
                                                   optional_forms)

        try:
            codes_map: Optional[Dict[
                str, Dict]] = self.download_definitions_from_s3(
                    f'{s3_prefix}/codes/', optional_forms)  # type: ignore
            # TODO - validate code mapping schema
        except DefinitionException as error:
            log.warning(error)
            codes_map = None

        if codes_map:
            diff_keys = set(schema.keys()) ^ (codes_map.keys())
            if diff_keys:
                raise DefinitionException(
                    'Rule definitions and codes definitions does not match, '
                    f'list of fields missing in one of the schemas: {diff_keys}'
                )

        return schema, codes_map

    def download_definitions_from_s3(  # noqa: C901
            self, prefix: str,
            optional_forms: Optional[Dict[str, bool]]) -> Dict[str, Mapping]:
        """Download rule definition files from a source S3 bucket and generate
        validation schema. For optional forms, there are two definition files
        in the S3 bucket. Load the appropriate definition depending on whether
        the form is submitted or not.

        Args:
            prefix: S3 path prefix
            optional_forms (optional): Submission status of each optional form

        Returns:
            dict[str, Mapping[str, object]: Schema object from rule definitions

        Raises:
            DefinitionException: If error occurred while loading rule definitions
        """

        full_schema: dict[str, Mapping] = {}

        # Handle missing / at end of prefix
        if not prefix.endswith('/'):
            prefix += '/'

        rule_defs = self.__s3_bucket.read_directory(prefix)
        if not rule_defs:
            message = ('Failed to load definitions from the S3 bucket: '
                       f'{self.__s3_bucket.bucket_name}/{prefix}')
            raise DefinitionException(message)

        parser_error = False
        for key, file_object in rule_defs.items():
            if optional_forms:
                # Select which file to load depending on form is submitted or not
                filename = key.removeprefix(prefix)
                formname = filename.partition('_')[0]
                optional_def = filename.endswith('_optional.json')

                if formname in optional_forms:
                    if optional_forms[formname]:  # form is submitted
                        if optional_def:
                            continue  # skip optional schema
                    else:  # form not submitted
                        if not optional_def:
                            continue  # skip regular schema

            if 'Body' not in file_object:
                log.error('Failed to load the rule definition file: %s', key)
                parser_error = True
                continue

            file_data = StringIO(file_object['Body'].read().decode('utf-8'))
            rules_type = 'json'
            if 'ContentType' in file_object:
                rules_type = file_object['ContentType']

            try:
                if 'json' in rules_type:
                    form_def = json.load(file_data)
                elif 'yaml' in rules_type:
                    form_def = yaml.safe_load(file_data)
                else:
                    log.error('Unhandled rule definition file type: %s - %s',
                              key, rules_type)
                    parser_error = True
                    continue

                # If there are any duplicate keys(i.e. variable names) across
                # forms, they will be replaced with the latest definitions.
                # It is assumed all variable names are unique within a project
                if form_def:
                    full_schema.update(form_def)
                    log.info('Parsed rule definition file: %s', key)
                else:
                    log.error('Empty rule definition file: %s', key)
                    parser_error = True
            except (JSONDecodeError, yaml.YAMLError, TypeError) as error:
                log.error('Failed to parse the rule definition file: %s - %s',
                          key, error)
                parser_error = True

        if parser_error:
            raise DefinitionException(
                'Error(s) occurred while loading rule definitions')

        return full_schema

    def get_optional_forms_submission_status(
            self, *, input_data: Dict[str, Any],
            module: str) -> Optional[Dict[str, bool]]:
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

        s3_client = self.__s3_bucket
        try:
            optional_forms = json.load(s3_client.read_data(self.__opfname))
        except s3_client.exceptions.NoSuchKey as error:
            message = (f'Optional forms file {self.__opfname} '
                       f'not found in S3 bucket {s3_client.bucket_name}')
            self.__error_writer.write(system_error(message, None))
            raise DefinitionException(message) from error
        except s3_client.exceptions.InvalidObjectState as error:
            message = f'Unable to access optional forms file {self.__opfname}: {error}'
            self.__error_writer.write(system_error(message, None))
            raise DefinitionException(message) from error
        except (JSONDecodeError, TypeError) as error:
            message = f'Error in reading optional forms file {self.__opfname}: {error}'
            self.__error_writer.write(system_error(message, None))
            raise DefinitionException(message) from error

        if not optional_forms or module not in optional_forms:
            log.warning('Cannot find optional forms info for module %s',
                        module)
            return None

        module_info = optional_forms[module]
        # some modules may not have separate packet codes, set to 'D' for default
        packet = input_data.get(FieldNames.PACKET, 'D')
        if packet not in module_info:
            log.warning('Cannot find optional forms info for packet %s/%s',
                        module, packet)
            return None

        packet_info: List[str] = module_info[packet]
        missing = []
        submission_status = {}
        for form in packet_info:
            mode_var = f'{FieldNames.MODE}{form}'
            if not input_data.get(mode_var):
                if self.__strict:
                    # TODO - change this to qc system error
                    self.__error_writer.write(empty_field_error(mode_var))
                    missing.append(mode_var)
                else:
                    submission_status[form] = False
                continue

            submission_status[form] = (input_data.get(mode_var)
                                       != DefaultValues.NOTFILLED)

        if missing:
            raise DefinitionException(
                f'Missing fields {missing} required to validate optional forms'
            )

        return submission_status
