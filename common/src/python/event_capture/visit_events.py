"""Defines a data model for visit event logging.

Supports tracking:
- visit data submission
- visit data deletion
- visit data passes QC
- visit data did not pass QC

Note: processes do not support issuing an explicit QC failure event.
"""

from datetime import datetime
from typing import Any, Literal, Self

from keys.types import DatatypeNameType
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ImageIdentification,
)
from pydantic import (
    BaseModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

VisitEventType = Literal["submit", "delete", "not-pass-qc", "pass-qc"]

# Visit Event Action constants
ACTION_SUBMIT = "submit"
ACTION_DELETE = "delete"
ACTION_NOT_PASS_QC = "not-pass-qc"
ACTION_PASS_QC = "pass-qc"


class VisitEvent(BaseModel):
    action: VisitEventType
    study: str = "adrc"
    project_label: str
    center_label: str
    gear_name: str
    data_identification: DataIdentification
    datatype: DatatypeNameType
    timestamp: datetime

    def __getattr__(self, name: str) -> Any:
        """Expose fields from data_identification for backward compatibility.

        Allows access to fields that were previously direct attributes of
        VisitEvent but are now part of the composed DataIdentification object.

        Supported fields:
        - ptid, naccid, adcid (from data_identification.participant)
        - visitnum (from data_identification.visit)
        - date (from data_identification.date)
        - module, packet (from data_identification.data if FormIdentification)
        - modality (from data_identification.data if ImageIdentification)
        - pipeline_adcid (alias for adcid)
        - visit_date (alias for date)
        - visit_number (alias for visitnum)
        """
        # Handle aliases for backward compatibility
        if name == "pipeline_adcid":
            return self.data_identification.adcid
        if name == "visit_date":
            return self.data_identification.date
        if name == "visit_number":
            return self.data_identification.visitnum

        # Delegate to data_identification's __getattr__
        # This handles: ptid, naccid, adcid, visitnum, date, module, packet, modality
        try:
            return getattr(self.data_identification, name)
        except AttributeError as error:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from error

    @model_serializer(mode="wrap")
    def serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        data = handler(self)

        # Extract and remove data_identification from serialized output
        data_identification = data.pop("data_identification")

        # Map DataIdentification fields to VisitEvent field names
        # adcid -> pipeline_adcid
        if "adcid" in data_identification:
            data["pipeline_adcid"] = data_identification["adcid"]

        # date -> visit_date
        if "date" in data_identification:
            data["visit_date"] = data_identification["date"]

        # visitnum -> visit_number
        if "visitnum" in data_identification:
            data["visit_number"] = data_identification["visitnum"]

        # Pass through fields that have the same name
        for field in ["ptid", "naccid", "module", "packet"]:
            if field in data_identification:
                data[field] = data_identification[field]

        return data

    @model_validator(mode="after")
    def validate_datatype_consistency(self) -> Self:
        """Validate that datatype field is consistent with
        data_identification.data type.

        - datatype="form" should have FormIdentification
        - datatype="dicom" should have ImageIdentification
        - Other datatypes should not have form-specific or image-specific data
        """
        data_obj = self.data_identification.data

        if self.datatype == "form":
            if not isinstance(data_obj, FormIdentification):
                raise ValueError(
                    f"Visit event has datatype 'form' but data_identification.data "
                    f"is {type(data_obj).__name__}"
                )
            if data_obj.module is None:
                raise ValueError("Visit event has datatype 'form' but module is None")

        elif self.datatype == "dicom":
            if not isinstance(data_obj, ImageIdentification):
                raise ValueError(
                    f"Visit event has datatype 'dicom' but data_identification.data "
                    f"is {type(data_obj).__name__}"
                )
            if data_obj.modality is None:
                raise ValueError(
                    "Visit event has datatype 'dicom' but modality is None"
                )

        else:
            # For other datatypes, ensure we don't have form or image specific data
            if isinstance(data_obj, (FormIdentification, ImageIdentification)):
                raise ValueError(
                    f"Visit event has datatype '{self.datatype}' but "
                    f"data_identification.data is {type(data_obj).__name__}"
                )

        return self
