"""Module for downloading and parsing rule definition schemas."""

import json
import logging
from io import StringIO
from json.decoder import JSONDecodeError
from typing import Dict, Mapping

import yaml
from s3.s3_client import S3BucketReader
from yaml.loader import SafeLoader

log = logging.getLogger(__name__)


# pylint: disable=(too-few-public-methods)
class Keys:
    """Class to store frquently accessed keys."""

    NACCID = 'naccid'
    MODULE = 'module'
    PACKET = 'packet'
    PTID = 'ptid'
    VISITNUM = 'visitnum'
    CODE = 'code'
    INDEX = 'index'
    COMPAT = 'compatibility'
    TEMPORAL = 'temporalrules'
    NULLABLE = 'nullable'
    REQUIRED = 'required'


class ParserException(Exception):
    """Raised when an error occurs during loading rule definitions."""


# pylint: disable=(too-few-public-methods)
class Parser:
    """Class to load the validation rules definitions as python objects."""

    def __init__(self, s3_bucket: S3BucketReader):
        """

        Args:
            s3_bucket (S3BucketReader): S3 bucket to load rule definitions
        """

        self.__s3_bucket = s3_bucket

    def download_rule_definitions(self, prefix: str) -> Dict[str, Mapping]:
        """Download rule definition files from a source S3 bucket and generate
        validation schema.

        Args:
            prefix (str): S3 path prefix

        Returns:
            dict[str, Mapping[str, object]: Schema object from rule definitions

        Raises:
            ParserException: If error occurred while loading rule definitions
        """

        full_schema: dict[str, Mapping] = {}

        # Handle missing / at end of prefix
        if not prefix.endswith('/'):
            prefix += '/'

        rule_defs = self.__s3_bucket.read_directory(prefix)
        if not rule_defs:
            message = ('Failed to load definitions from the S3 bucket: '
                       f'{self.__s3_bucket.bucket_name}/{prefix}')
            raise ParserException(message)

        parser_error = False
        for key, file_object in rule_defs.items():
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
                    form_def = yaml.load(file_data, Loader=SafeLoader)
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
            raise ParserException(
                'Error(s) occurred while loading rule definitions')

        return full_schema
