"""
Helper classes to aid with the FormPreprocessor.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from keys.keys import (
    FieldNames,
    SysErrorCodes,
)
from outputs.error_models import VisitKeys
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    preprocess_errors,
    preprocessing_error,
)
from uploads.acquisition import is_duplicate_dict

log = logging.getLogger(__name__)


class PreprocessingException(Exception):
    pass


@dataclass
class PreprocessingContext:
    input_record: Dict[str, Any]
    line_num: int
    subject_lbl: Optional[str] = None
    ivp_record: Optional[Dict[str, Any]] = None


class FormPreprocessorErrorHandler:
    """Class to handle writing preprocessing errors."""

    def __init__(
        self,
        module: str,
        module_configs: ModuleConfigs,
        error_writer: ErrorWriter
    ) -> None:
        self.__module = module
        self.__module_configs = module_configs
        self.__error_writer = error_writer

    def write_preprocessing_error(self,
                                  field: FieldNames,
                                  value: Any,
                                  pp_context: PreprocessingContext,
                                  error_code: SysErrorCodes,
                                  suppress_logs: bool = False,
                                  message: str = None,
                                  extra_args: Optional[List[Any]] = None) -> None:
        """Write a preprocessing error.

        Args:
            field: The field that failed
            value: Value of the failed field
            pp_context: PreprocessingContext
            error_code: The specific error code to report
            record: The record to report; defaults to current input record
            suppress_logs: Whether or not to suppress stderr logs (set to
                True if providing own error logs to stderr)
            message: Alternative error message
            extra_args: Extra args to provide
        """
        input_record = pp_context.input_record
        if not suppress_logs:
            stderr_msg = (
                "%s - %s/%s/%s",
                preprocess_errors.get(error_code, "Preprocessing error"),
                self.__module,
                input_record[FieldNames.FORMVER],
                input_record[FieldNames.PACKET],
            )

            if extra_args:
                stderr_msg = f"{stderr_msg} - {', '.join(extra_args)}"

            log.error(stderr_msg)

        self.__error_writer.write(
            field=field,
            value=value,
            line=pp_context.line_num,
            error_code=error_code,
            message=message,
            visit_keys=VisitKeys.create_from(
                record=record, date_field=self.__module_configs.date_field
            ),
            extra_args=extra_args
        )

    def write_packet_error(self,
                           pp_context: PreprocessingContext,
                           error_code: SysErrorCodes,
                           suppress_logs: bool = False) -> None:
        """Write a packet-related preprocessing error."""
        packet = input_record[FieldNames.PACKET]
        self.write_preprocessing_error(
            field=FieldNames.PACKET,
            value=packet,
            pp_context=pp_context,
            error_code=error_code,
            suppress_logs=suppress_logs)

    def write_module_error(self,
                           pp_context: PreprocessingContext,
                           error_code: SysErrorCodes,
                           suppress_logs: bool = False,
                           message: str = None) -> None:
        """Write a module-related preprocessing error."""
        self.write_preprocessing_error(
            field=FieldNames.MODULE,
            value=self.__module,
            pp_context=pp_context,
            error_code=error_code,
            suppress_logs=suppress_logs,
            message=message)

    def write_visitnum_error(self,
                             pp_context: PreprocessingContext,
                             error_code: SysErrorCodes) -> None:
        """Write a packet-related preprocessing error."""
        visitnum = input_record[FieldNames.VISITNUM]
        self.write_preprocessing_error(
            field=FieldNames.VISITNUM,
            value=visitnum,
            pp_context=pp_context,
            error_code=error_code)

    def write_date_error(self,
                         pp_context: PreprocessingContext,
                         error_code: SysErrorCodes) -> None:
        """Write a date-related preprocessing error."""
        input_record = pp_context.input_record
        date_field = self.__module_configs.date_field
        date_value = input_record[date_field]

        self.write_preprocessing_error(
            field=date_field,
            value=date_value,
            pp_context=pp_context,
            error_code=error_code)
