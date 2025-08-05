"""Utilities for writing errors to a error log."""

import logging
from typing import Any, List, Literal, Optional

from keys.keys import SysErrorCodes

from outputs.error_models import CSVLocation, FileError, JSONLocation

log = logging.getLogger(__name__)


preprocess_errors = {
    SysErrorCodes.ADCID_MISMATCH: (
        "ADCID must match the ADCID of the center uploading the data"
    ),
    SysErrorCodes.IVP_EXISTS: (
        "Only one Initial Visit Packet is allowed per participant"
    ),
    SysErrorCodes.UDS_NOT_MATCH: (
        "Cannot find a matching UDS visit packet with the "
        "same visit number and visit date as the module packet"
    ),
    SysErrorCodes.INVALID_MODULE_PACKET: (
        "Follow-up module packet cannot be submitted for a UDS initial visit packet (I)"
    ),
    SysErrorCodes.UDS_NOT_EXIST: (
        "A UDS packet must be submitted before submitting this module/form"
    ),
    SysErrorCodes.DIFF_VISITDATE: (
        "Two packets cannot have the same visit number (VISITNUM) "
        "if they are from different dates (VISITDATE)"
    ),
    SysErrorCodes.DIFF_VISITNUM: (
        "Two packets cannot have the same visit date (VISITDATE) "
        "if they are from different visit numbers (VISITNUM)"
    ),
    SysErrorCodes.LOWER_FVP_VISITNUM: (
        "Visit number (VISITNUM) for Follow-Up Visit Packets must be "
        "greater than Visit number (VISITNUM) for Initial Visit Packet"
    ),
    SysErrorCodes.LOWER_I4_VISITNUM: (
        "Visit number (VISITNUM) for UDSv4 Initial Visit Packet (PACKET=I4) "
        "must be greater than Visit number (VISITNUM) for of the last "
        "UDSv3 Visit Packet"
    ),
    SysErrorCodes.LOWER_FVP_VISITDATE: (
        "Follow-Up Packet visit date (VISITDATE) cannot be equal to "
        "or from a date before the Initial Visit Packet"
    ),
    SysErrorCodes.LOWER_I4_VISITDATE: (
        "Visit date (VISITDATE) for UDSv4 Initial Visit Packet (PACKET=I4) "
        "must be a date after the last UDSv3 Visit Packet"
    ),
    SysErrorCodes.EXCLUDED_FIELDS: (
        "Following fields in the input record do not match "
        "with the submitted version/packet of the form/module: {0}"
    ),
    SysErrorCodes.INVALID_PACKET: (
        "Provided PACKET code is not in the list of accepted packets for this module"
    ),
    SysErrorCodes.INVALID_VERSION: (
        "Provided FORMVER is not in the list of accepted versions for this module"
    ),
    SysErrorCodes.INVALID_PTID: ("PTID must be no more than 10 characters"),
    SysErrorCodes.INVALID_MODULE: (
        "Provided MODULE is not in the list of currently accepted modules"
    ),
    SysErrorCodes.MISSING_IVP: (
        "Follow-Up visit cannot be submitted without an existing Initial Visit Packet"
    ),
    SysErrorCodes.MULTIPLE_IVP: (
        "More than one IVP packet found for the participant/module"
    ),
    SysErrorCodes.UDS_NOT_APPROVED: (
        "UDS visit packet must be approved before the module visit can be processed"
    ),
    SysErrorCodes.MISSING_UDS_V3: (
        "To submit an Initial UDSv4 Visit Packet (PACKET=I4), "
        "participant must have an existing UDSv3 Visit Packet"
    ),
    SysErrorCodes.MISSING_UDS_I4: (
        "Participant must have an existing Initial UDSv4 Visit Packet (PACKET=I4) "
        "submitted before the Follow-Up Visit Packet (PACKET=F)"
    ),
    SysErrorCodes.DUPLICATE_VISIT: (
        "Duplicate record with the same visit date exists in the batch CSV file "
        "for this participant"
    ),
    SysErrorCodes.LOWER_VISITNUM: (
        "Packet with higher visit date (VISITDATE) "
        "must also have a higher visit number (VISITNUM)"
    ),
    SysErrorCodes.MISSING_SUBMISSION_STATUS: (
        "Missing submission status (MODE<form name>) variables {0}"
        "for one or more optional forms"
    ),
}


def identifier_error(
    line: int, value: str, field: str = "ptid", message: Optional[str] = None
) -> FileError:
    """Creates a FileError for an unrecognized PTID error in a CSV file.

    Tags the error type as 'error:identifier'

    Args:
      line: the line where error occurred
      value: the value of the PTID
    Returns:
      a FileError object initialized for an identifier error
    """
    error_message = message if message else "Unrecognized participant ID"
    return FileError(
        error_type="error",
        error_code="identifier-error",
        location=CSVLocation(line=line, column_name=field),
        value=value,
        message=error_message,
    )


def empty_file_error() -> FileError:
    """Creates a FileError for an empty input file."""
    return FileError(
        error_type="error", error_code="empty-file", message="Empty input file"
    )


def missing_header_error() -> FileError:
    """Creates a FileError for a missing header."""
    return FileError(
        error_type="error", error_code="missing-header", message="No file header found"
    )


def invalid_header_error(message: Optional[str] = None) -> FileError:
    """Creates a FileError for an invalid header."""
    message = message if message else "Invalid header"
    return FileError(error_type="error", error_code="invalid-header", message=message)


def missing_field_error(field: str | set[str]) -> FileError:
    """Creates a FileError for missing field(s) in header."""
    return FileError(
        error_type="error",
        error_code="missing-field",
        message=f"Missing one or more required field(s) {field} in the header",
    )


def empty_field_error(
    field: str | set[str], line: Optional[int] = None, message: Optional[str] = None
) -> FileError:
    """Creates a FileError for empty field(s)."""
    error_message = message if message else f"Required field(s) {field} cannot be blank"

    return FileError(
        error_type="error",
        error_code="empty-field",
        location=CSVLocation(line=line, column_name=str(field))
        if line
        else JSONLocation(key_path=str(field)),
        message=error_message,
    )


def malformed_file_error(error: str) -> FileError:
    """Creates a FileError for a malformed input file."""
    return FileError(
        error_type="error",
        error_code="malformed-file",
        message=f"Malformed input file: {error}",
    )


def unexpected_value_error(
    field: str,
    value: str,
    expected: str,
    line: Optional[int] = None,
    message: Optional[str] = None,
) -> FileError:
    """Creates a FileError for an unexpected value.

    Args:
      field: the field name
      value: the unexpected value
      expected: the expected value
      line: the line number
      message: the error message
    Returns:
      the constructed FileError
    """
    error_message = message if message else (f"Expected {expected} for field {field}")

    return FileError(
        error_type="error",
        error_code="unexpected-value",
        value=value,
        expected=expected,
        location=CSVLocation(line=line, column_name=str(field))
        if line
        else JSONLocation(key_path=str(field)),
        message=error_message,
    )


def unknown_field_error(field: str | set[str]) -> FileError:
    """Creates a FileError for unknown field(s) in file header."""
    return FileError(
        error_type="error",
        error_code="unknown-field",
        message=f"Unknown field(s) {field} in header",
    )


def system_error(
    message: str,
    error_location: Optional[CSVLocation | JSONLocation] = None,
    error_type: Literal["alert", "error", "warning"] = "error",
) -> FileError:
    """Creates a FileError object for a system error.

    Args:
      message: error message
      error_location (optional): CSV or JSON file location related to the error
      error_type: error type, defaults to "error"
    Returns:
      a FileError object initialized for system error
    """
    return FileError(
        error_type=error_type,
        error_code="system-error",
        location=error_location,
        message=message,
    )


def previous_visit_failed_error(prev_visit: str) -> FileError:
    """Creates a FileError when participant has failed previous visits."""
    return FileError(
        error_type="error",
        error_code="failed-previous-visit",
        message=(
            f"Visit file {prev_visit} has to be approved "
            "before evaluating any subsequent visits"
        ),
    )


def non_utf8_file_error() -> FileError:
    """Creates a FileError when a non-utf8 file is attempted to be read."""
    return FileError(
        error_type="error",
        error_code="non-utf8-encoding",
        message="File must be UTF-8-compliant",
    )


def preprocessing_error(
    field: str,
    value: str,
    line: Optional[int] = None,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
    ptid: Optional[str] = None,
    visitnum: Optional[str] = None,
    extra_args: Optional[List[Any]] = None,
) -> FileError:
    """Creates a FileError for pre-processing error.

    Args:
      field: the field name
      value: the value
      line (optional): the line number
      error_code (optional): pre-processing error code
      message (optional): the error message
      ptid (optional): PTID if known
      visitnum (optional): visitnum if known

    Returns:
      the constructed FileError
    """

    error_message = (
        message
        if message
        else (f"Pre-processing error for field {field} value {value}")
    )

    if error_code:
        error_message = preprocess_errors.get(error_code, error_message)

    if extra_args:
        error_message = error_message.format(*extra_args)

    return FileError(
        error_type="error", # pyright: ignore[reportCallIssue]
        error_code=error_code if error_code else "preprocess-error", # pyright: ignore[reportCallIssue]
        value=value,
        location=CSVLocation(line=line, column_name=field)
        if line
        else JSONLocation(key_path=field),
        message=error_message,
        ptid=ptid,
        visitnum=visitnum,
    )


def partially_failed_file_error() -> FileError:
    """Creates a FileError when input file is not fully approved."""
    return FileError(
        error_type="error", # pyright: ignore[reportCallIssue]
        error_code="partially-failed", # pyright: ignore[reportCallIssue]
        message=(
            "Some records in this file did not pass validation, "
            "check the respective record level qc status"
        ),
    )


def existing_participant_error(
    field: str, value: str, line: int, message: Optional[str] = None
) -> FileError:
    """Creates a FileError for unexpected existing participant."""
    error_message = message if message else (f"Participant exists for PTID {value}")
    return FileError(
        error_type="error", # pyright: ignore[reportCallIssue]
        error_code="participant-exists", # pyright: ignore[reportCallIssue]
        location=CSVLocation(column_name=field, line=line),
        message=error_message,
    )
