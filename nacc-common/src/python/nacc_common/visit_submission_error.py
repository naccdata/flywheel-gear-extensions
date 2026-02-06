"""Definitions for error reports."""

from typing import Any

from flywheel.models.file_entry import FileEntry
from pydantic import SerializerFunctionWrapHandler, model_serializer

from nacc_common.error_models import CSVLocation, FileError, JSONLocation, VisitKeys
from nacc_common.qc_report import (
    ErrorReportVisitor,
    QCReportBaseModel,
    QCTransformerError,
    extract_visit_keys,
)

ModuleName = str


class ErrorReportModel(QCReportBaseModel, FileError):
    """Data model for error reports."""

    adcid: int
    module: ModuleName

    @model_serializer(mode="wrap")
    def serialize_model(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Creates a dictionary for an error report model with location field
        replaced by fields from the location object.

        Uses a handler that does the standard serialization and then modifies
        the result.

        Args:
          handler: the "plain" serializer
        """
        report_model = handler(self)  # use standard serialization
        location: dict[str, Any] = report_model.pop("location", {})
        if location:
            report_model.update(location)

        return report_model

    @classmethod
    def serialized_fieldnames(cls) -> list[str]:
        """Returns the list of fieldnames in the serialized error report
        object.

        Ensures CSV created from any object will have corresponding
        fieldnames. Removes location and replaces with the field names
        from CSVLocation and JSONLocation.
        """
        fieldnames = set(cls.fieldnames())
        csv_fields = set(CSVLocation.model_fields.keys())
        json_fields = set(JSONLocation.model_fields.keys())

        return list((fieldnames - {"location"}).union(csv_fields).union(json_fields))


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

    error_model = file_error.model_dump()

    return ErrorReportModel.model_validate(
        {
            "adcid": visit.adcid,
            "module": visit.module,
            "stage": gear_name,
            **error_model,
        }
    )


def error_report_visitor_builder(file: FileEntry, adcid: int) -> ErrorReportVisitor:
    visit = extract_visit_keys(file)
    visit.adcid = adcid
    return ErrorReportVisitor(visit=visit, transformer=error_transformer)
