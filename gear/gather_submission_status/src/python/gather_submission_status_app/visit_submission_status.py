"""Definitions for status reports."""

from typing import Optional

from outputs.error_models import QCStatus, ValidationModel, VisitKeys
from outputs.qc_report import (
    QCReportBaseModel,
    QCTransformerError,
)


class StatusReportModel(QCReportBaseModel):
    """Data model for status reports."""

    ptid: str
    module: str
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
    if visit.ptid is None or visit.module is None or visit.date is None:
        raise QCTransformerError("Cannot generate status incomplete visit details")

    return StatusReportModel(
        ptid=visit.ptid,
        module=visit.module,
        visitdate=visit.date,
        stage=gear_name,
        status=validation_model.state,
    )
