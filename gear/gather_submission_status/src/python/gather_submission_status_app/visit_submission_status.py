"""Definitions for status reports."""

from typing import Optional, get_args

from keys.types import ModuleName
from outputs.error_models import QCStatus, ValidationModel, VisitKeys
from outputs.qc_report import (
    QCReportBaseModel,
    QCTransformerError,
)


class StatusReportModel(QCReportBaseModel):
    """Data model for status reports."""

    adcid: int
    ptid: str
    module: ModuleName
    visitdate: str
    status: Optional[QCStatus] = None


def status_transformer(
    gear_name: str, visit: VisitKeys, validation_model: ValidationModel
) -> StatusReportModel:
    """Transformer for creating status report objects from a file QC validation
    model.

    The status record includes:
    - visit details for the file,
    - the name of the gear to which the validation model is associated, and
    - the status from the validation model

    Args:
      gear_name: the gear name corresponding to validation model
      visit: the visit attributes for the file
      validation_model: the validation model

    Raises:
      QCTransformerError if the visit ptid, module and date are not set
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

    return StatusReportModel(
        adcid=visit.adcid,
        ptid=visit.ptid,
        module=visit.module,  # pyright: ignore[reportArgumentType]
        visitdate=visit.date,
        stage=gear_name,
        status=validation_model.state,
    )
