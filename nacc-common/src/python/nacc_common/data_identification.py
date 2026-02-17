from typing import Any, Optional, Self

from pydantic import (
    BaseModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
)

from nacc_common.field_names import FieldNames


class ParticipantIdentification(BaseModel):
    """Identifies a participant and their center."""

    adcid: Optional[int] = None
    ptid: Optional[str] = None
    naccid: Optional[str] = None

    @classmethod
    def from_form_record(cls, record: dict[str, Any]) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        """
        return cls(
            adcid=record.get(FieldNames.ADCID),
            ptid=record.get(FieldNames.PTID),
            naccid=record.get(FieldNames.NACCID),
        )


class VisitIdentification(BaseModel):
    """Identifies a specific visit."""

    visitnum: Optional[str] = None

    @classmethod
    def from_form_record(cls, record: dict[str, Any]) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        """
        return cls(visitnum=record.get(FieldNames.VISITNUM))


class FormIdentification(BaseModel):
    """Identifies form-specific data."""

    module: Optional[str] = None  # Form name (A1, B1, NP, Milestone, etc.)
    packet: Optional[str] = None  # I=Initial, F=Followup, T=Telephone

    @classmethod
    def from_form_record(cls, record: dict[str, Any]) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        """
        return cls(
            module=record.get(FieldNames.MODULE), packet=record.get(FieldNames.PACKET)
        )


class ImageIdentification(BaseModel):
    """Identifies image-specific data."""

    modality: Optional[str] = None  # Imaging modality (MR, CT, PET, etc.)


class DataIdentification(BaseModel):
    """Base class for all data identification using composition.

    Combines participant identification with optional visit
    identification. This replaces the legacy VisitKeys class.
    """

    participant: ParticipantIdentification
    date: Optional[str] = None
    visit: Optional[VisitIdentification] = None
    data: Optional[FormIdentification | ImageIdentification] = None

    @classmethod
    def from_visit_metadata(
        cls,
        adcid: Optional[int] = None,
        ptid: Optional[str] = None,
        naccid: Optional[str] = None,
        visitnum: Optional[str] = None,
        date: Optional[str] = None,
        module: Optional[str] = None,
        packet: Optional[str] = None,
        modality: Optional[str] = None,
    ) -> "DataIdentification":
        """Create DataIdentification from flat visit metadata fields.

        This is a convenience method for backward compatibility with code
        that uses the legacy flat structure.

        Args:
            adcid: Center identifier
            ptid: Participant identifier (center-assigned)
            naccid: Participant identifier (NACC-assigned)
            visitnum: Visit sequence number
            date: Visit date or collection date
            module: Form name or imaging modality
            packet: Form packet (I/F/T)
            modality: Imaging modality (alternative to module for images)

        Returns:
            DataIdentification with composed structure
        """
        participant = ParticipantIdentification(
            adcid=adcid,
            ptid=ptid,
            naccid=naccid,
        )

        # Always create visit object to ensure visitnum field is present in serialization
        visit = VisitIdentification(visitnum=visitnum)

        # Create data object - default to FormIdentification for backward compatibility
        # unless modality is explicitly provided (indicating image data)
        data: FormIdentification | ImageIdentification | None = None
        if modality is not None:
            data = ImageIdentification(modality=modality)
        else:
            # Always create FormIdentification to ensure module/packet fields are present
            data = FormIdentification(module=module, packet=packet)

        return cls(participant=participant, date=date, visit=visit, data=data)

    def __getattr__(self, attribute_name: str) -> Optional[Any]:
        # Check participant
        if hasattr(self.participant, attribute_name):
            return getattr(self.participant, attribute_name)

        # Check visit (may be None)
        if self.visit is not None and hasattr(self.visit, attribute_name):
            return getattr(self.visit, attribute_name)

        # Check data (may be None)
        if self.data is not None and hasattr(self.data, attribute_name):
            return getattr(self.data, attribute_name)

        raise AttributeError(
            f"No attribute {attribute_name} for DataIdentification object"
        )

    @model_serializer(mode="wrap")
    def serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        data = handler(self)

        # Flatten nested structures - pop by actual field names, not aliases
        # The handler already applied aliases, so nested dicts have aliased keys
        for field_name in ["participant", "visit", "data"]:
            value = data.pop(field_name, None)
            if value is None:
                continue
            if not isinstance(value, dict):
                continue

            # Merge the nested dict into the parent
            for k, v in value.items():
                data[k] = v

        return data

    @classmethod
    def from_form_record(
        cls, record: dict[str, Any], date_field: Optional[str] = None
    ) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        """
        return cls(
            participant=ParticipantIdentification.from_form_record(record),
            date=record.get(date_field) if date_field is not None else None,
            visit=VisitIdentification.from_form_record(record),
            data=FormIdentification.from_form_record(record),
        )

    @classmethod
    def from_visit_info(cls, file_entry) -> Optional["DataIdentification"]:
        """Factory method to create DataIdentification from a FileEntry.

        Args:
          file_entry: the file entry
        Returns:
          the DataIdentification instance if there is visit metadata. None, otherwise.
        """
        file_entry = file_entry.reload()
        if not file_entry.info:
            return None

        visit_data = file_entry.info.get("visit")
        if not visit_data:
            return None

        try:
            return DataIdentification.model_validate(visit_data)
        except ValidationError:
            return None

    @classmethod
    def fieldnames(cls) -> list[str]:
        """Gathers the serialized field names for the class."""
        result: list[str] = []
        for fieldname, field_info in cls.model_fields.items():
            if field_info.serialization_alias:
                result.append(field_info.serialization_alias)
            else:
                result.append(fieldname)
        return result


# VisitKeys = DataIdentification
#   create_from -> from_form_record
# VisitMetadata = DataIdentification
# .  create -> from_visit_info
# ImageVisitMetadata = DataIdentification
