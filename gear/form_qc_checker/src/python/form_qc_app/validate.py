"""Helper class for validating a visit."""

from typing import Any, Dict, List, Mapping, Optional

from nacc_form_validator.quality_check import QualityCheck
from outputs.errors import ErrorWriter

from form_qc_app.error_info import ErrorComposer, ErrorStore


class RecordValidator:
    """Validate the data record using nacc-form-validator library
    (https://github.com/naccdata/nacc-form-validator)"""

    def __init__(
        self,
        *,
        qual_check: QualityCheck,
        error_store: ErrorStore,
        error_writer: ErrorWriter,
        codes_map: Optional[Dict[str, Dict]] = None,
    ):
        """Initialize RecordValidator.

        Args:
            qual_check: NACC data quality checker object
            error_store: database connection to retrieve NACC QC chek info
            error_writer: error writer object to output error metadata
            codes_map(optional): schema to map NACC QC checks to validation errors
        """
        self.__qc = qual_check
        self.__error_store = error_store
        self.__error_writer = error_writer
        self.__codes_map = codes_map

    def get_validation_schema(self) -> Dict[str, Mapping]:
        """Returns the schema definition used for data validation."""
        return self.__qc.schema

    def compose_error_metadata(
        self,
        *,
        input_record: Dict[str, str],
        sys_failure: bool,
        dict_errors: Dict[str, List[str]],
        error_tree: Optional[Dict[str, Any]],
        line_number: Optional[int],
    ):
        """Compose error metadata using validation errors and error code
        mapping.

        Args:
            input_record: input data record
            sys_failure: True if any system errors occurred during validation
            dict_errors: Dict of formatted error messages by variable
            error_tree: dict like object containing validation error details
            line_number: line # in CSV file if the record is from CSV
        """

        error_messages = self.__qc.validator.get_error_messages()
        error_composer = ErrorComposer(
            input_data=input_record,
            error_store=self.__error_store,
            dict_errors=dict_errors,
            error_messages=error_messages,
            error_writer=self.__error_writer,
        )

        if sys_failure:
            error_composer.compose_system_errors_metadata(line_number)
        elif self.__codes_map and error_tree is not None:
            error_composer.compose_detailed_error_metadata(
                error_tree=error_tree,
                err_code_map=self.__codes_map,
                line_number=line_number,
            )
        else:
            error_composer.compose_minimal_error_metadata(line_number)

    def process_data_record(
        self, *, record: Dict[str, str], line_number: Optional[int] = None
    ) -> bool:
        """Process the input record and report any errors.

        Args:
            record: input data record
            line_number (optional): line # in CSV file if the record is from CSV

        Returns:
            bool: True if record passed NACC data quality checks, else False
        """

        valid, sys_failure, dict_errors, error_tree = self.__qc.validate_record(record)

        if not valid:
            self.compose_error_metadata(
                input_record=record,
                sys_failure=sys_failure,
                dict_errors=dict_errors,
                error_tree=error_tree,  # type: ignore
                line_number=line_number,
            )

        return valid
