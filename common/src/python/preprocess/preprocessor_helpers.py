"""Helper classes to aid with the FormPreprocessor."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from dates.form_dates import build_date
from nacc_common.error_models import VisitKeys
from nacc_common.field_names import (
    FieldNames,
)
from outputs.error_writer import ErrorWriter
from outputs.errors import (
    preprocess_errors,
    preprocessing_error,
)

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
        self, module: str, module_configs: ModuleConfigs, error_writer: ErrorWriter
    ) -> None:
        self.__module = module
        self.__module_configs = module_configs
        self.__error_writer = error_writer

    def write_preprocessing_error(
        self,
        field: str,
        value: Any,
        pp_context: PreprocessingContext,
        error_code: str,
        suppress_logs: bool = False,
        message: Optional[str] = None,
        extra_args: Optional[List[Any]] = None,
    ) -> None:
        """Write a preprocessing error.

        Args:
            field: The field that failed
            value: Value of the failed field
            pp_context: PreprocessingContext
            error_code: The specific error code to report
            suppress_logs: Whether or not to suppress stderr logs (set to
                True if providing own error logs to stderr)
            message: Alternative error message
            extra_args: Extra args to provide
        """
        input_record = pp_context.input_record
        if not suppress_logs:
            error_msg = preprocess_errors.get(error_code, "Preprocessing error")
            stderr_msg = (
                f"{error_msg} - {self.__module}/{input_record[FieldNames.FORMVER]}"
            )

            packet = input_record.get(FieldNames.PACKET)
            if packet:
                stderr_msg = f"{stderr_msg}/{packet}"

            if extra_args:
                stderr_msg = f"{stderr_msg} - {extra_args}"

            log.error(stderr_msg)

        self.__error_writer.write(
            preprocessing_error(
                field=field,
                value=value,
                line=pp_context.line_num,
                error_code=error_code,
                message=message,
                visit_keys=VisitKeys.create_from(
                    record=input_record, date_field=self.__module_configs.date_field
                ),
                extra_args=[extra_args],
            )
        )

    def write_packet_error(
        self,
        pp_context: PreprocessingContext,
        error_code: str,
        suppress_logs: bool = False,
    ) -> None:
        """Write a packet-related preprocessing error."""
        input_record = pp_context.input_record
        packet = input_record[FieldNames.PACKET]
        self.write_preprocessing_error(
            field=FieldNames.PACKET,
            value=packet,
            pp_context=pp_context,
            error_code=error_code,
            suppress_logs=suppress_logs,
        )

    def write_module_error(
        self,
        pp_context: PreprocessingContext,
        error_code: str,
        suppress_logs: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """Write a module-related preprocessing error."""
        self.write_preprocessing_error(
            field=FieldNames.MODULE,
            value=self.__module,
            pp_context=pp_context,
            error_code=error_code,
            suppress_logs=suppress_logs,
            message=message,
        )

    def write_visitnum_error(
        self, pp_context: PreprocessingContext, error_code: str
    ) -> None:
        """Write a visitnum-related preprocessing error."""
        input_record = pp_context.input_record
        visitnum = input_record[FieldNames.VISITNUM]
        self.write_preprocessing_error(
            field=FieldNames.VISITNUM,
            value=visitnum,
            pp_context=pp_context,
            error_code=error_code,
        )

    def write_formver_error(
        self, pp_context: PreprocessingContext, error_code: str
    ) -> None:
        """Write a formver-related preprocessing error."""
        input_record = pp_context.input_record
        version = input_record[FieldNames.FORMVER]
        self.write_preprocessing_error(
            field=FieldNames.FORMVER,
            value=version,
            pp_context=pp_context,
            error_code=error_code,
        )

    def write_date_error(
        self,
        pp_context: PreprocessingContext,
        error_code: str,
        date_field: Optional[str] = None,
    ) -> None:
        """Write a date-related preprocessing error."""
        if not date_field:
            date_field = self.__module_configs.date_field

        input_record = pp_context.input_record
        date_value = input_record[date_field]

        self.write_preprocessing_error(
            field=date_field,
            value=date_value,
            pp_context=pp_context,
            error_code=error_code,
        )


def validate_sex_reported_on_np(npsex: int, uds_record: Dict[str, Any]) -> bool:
    """Check whether participant's sex reported on NP form and UDS IVP matches.

    Args:
        npsex: participant's sex reported on NP form
        uds_record: UDS IVP packet for participant

    Returns:
        bool: True if UDS and NP values match
    """

    sex = uds_record.get(FieldNames.SEX)
    if not sex:
        sex = uds_record.get(FieldNames.BIRTHSEX)

    if not sex:
        return False

    if int(sex) in [1, 2] and npsex in [1, 2]:
        return sex == npsex

    return True


def validate_age_at_death(
    np_dod: datetime, np_dage: int, uds_record: Dict[str, Any]
) -> bool:
    """Check whether age at death reported on NP form matches with the age at
    death calculated using DOB reported on UDS IVP.

    Args:
        np_dod: date of death reported on NP form
        np_dage: age at death reported on NP form
        uds_record: UDS IVP packet for participant

    Returns:
        bool: True if UDS and NP values match
    """

    birthyr = uds_record.get("birthyr")
    birthmo = uds_record.get("birthmo")

    if not (birthyr and birthmo):
        return False

    dob = build_date(year=birthyr, month=birthmo, day="1")
    if not dob:
        return False

    # age calculation is based off of how RT has defined it in A1
    nacc_dage = round((np_dod - dob).days / 365.25)

    return abs(nacc_dage - np_dage) <= 1
