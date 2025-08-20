"""Definitions for error reports."""

from typing import Any, get_args

from keys.types import ModuleName
from outputs.error_models import FileError, VisitKeys
from outputs.qc_report import QCReportBaseModel, QCTransformerError


class ErrorReportModel(QCReportBaseModel, FileError):
    """Data model for error reports."""

    adcid: int
    module: ModuleName


def error_transformer(
    gear_name: str, visit: VisitKeys, file_error: FileError
) -> ErrorReportModel:
    """Transformer for creating error report objects from a file QC validation
    model.

    The error record includes:
    - visit details for the file
    - the name of the gear to which the error model is associated, and
    - the error details.

    Args:
      gear_name: the gear name corresponding to the file error model
      visit: the visit attributes for the file
      file_error: the error model

    Raises:
      QCTransformerError if the visit details are not set
    """
    if (
        visit.adcid is None
        or visit.ptid is None
        or visit.module is None
        or visit.date is None
    ):
        raise QCTransformerError("Cannot generate status incomplete visit details")

    if visit.module not in get_args(ModuleName):
        raise QCTransformerError(f"Unexpected module name: {visit.module}")

    error_model = file_error.model_dump()
    location: dict[str, Any] = error_model.pop("location", {})
    if location:
        error_model.update(location)

    return ErrorReportModel.model_validate(
        {
            "adcid": visit.adcid,
            "module": visit.module,
            "stage": gear_name,
            **error_model,
        }
    )
