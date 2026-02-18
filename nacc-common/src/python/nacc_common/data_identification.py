from typing import Any, Optional, Self

from dates.form_dates import DEFAULT_DATE_FORMAT, convert_date
from identifiers.model import PTID_PATTERN
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_validator,
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
        visitnum = record.get(FieldNames.VISITNUM)
        # Convert empty string to None
        if visitnum == "":
            visitnum = None
        return cls(visitnum=visitnum)


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
        module = record.get(FieldNames.MODULE)
        if module is None:
            raise EmptyFieldError(FieldNames.MODULE)

        packet = record.get(FieldNames.PACKET)
        # Convert empty string to None
        if packet == "":
            packet = None

        return cls(module=record.get(FieldNames.MODULE), packet=packet)

    @field_validator("module", "packet")
    @classmethod
    def normalize_module(cls, v: Optional[str]) -> Optional[str]:
        """Normalize module to uppercase for canonical storage and matching.

        This ensures consistency with EventMatchKey matching logic and
        provides case-insensitive module handling throughout the system.

        Args:
            v: The module value

        Returns:
            Module normalized to uppercase, or None if input is None
        """
        return v.upper() if v else v


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
        ptid: Optional[str] = Field(None, max_length=10, pattern=PTID_PATTERN),
        naccid: Optional[str] = None,
        visitnum: Optional[str] = None,
        date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
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

        # Always create visit object to ensure visitnum field is present
        visit = VisitIdentification(visitnum=visitnum)

        # Create data object - default to FormIdentification for backward compatibility
        # unless modality is explicitly provided (indicating image data)
        data: FormIdentification | ImageIdentification | None = None
        # Always create FormIdentification so that have module/packet fields
        data = FormIdentification(module=module, packet=packet)
        if modality is not None:
            data = ImageIdentification(modality=modality)

        return cls(participant=participant, date=date, visit=visit, data=data)

    def with_updates(
        self,
        adcid: Optional[int] = None,
        packet: Optional[str] = None,
        visitnum: Optional[str] = None,
    ) -> "DataIdentification":
        """Return a copy of this DataIdentification with specified fields
        updated.

        Only updates fields that are explicitly provided (not None).
        This is useful for backfilling missing data from different sources.

        Args:
            adcid: Center identifier to update
            packet: Form packet (I/F/T) to update
            visitnum: Visit sequence number to update

        Returns:
            New DataIdentification instance with updated fields
        """
        updates: dict[str, Any] = {}

        # Update participant.adcid if provided
        if adcid is not None:
            updates["participant"] = self.participant.model_copy(
                update={"adcid": adcid}
            )

        # Update visit.visitnum if provided
        if visitnum is not None:
            if self.visit is not None:
                updates["visit"] = self.visit.model_copy(update={"visitnum": visitnum})
            else:
                updates["visit"] = VisitIdentification(visitnum=visitnum)

        # Update data.packet if provided (only for FormIdentification)
        if packet is not None:
            if self.data is not None and isinstance(self.data, FormIdentification):
                updates["data"] = self.data.model_copy(update={"packet": packet})
            elif self.data is None:
                # Create FormIdentification with just packet
                updates["data"] = FormIdentification(packet=packet)

        return self.model_copy(update=updates)

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
    def from_form_record(cls, record: dict[str, Any], date_field: str) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        """
        date = record.get(date_field) if date_field is not None else None
        if date is None:
            raise EmptyFieldError(date_field)
        normalized_date = convert_date(
            date_string=date, date_format=DEFAULT_DATE_FORMAT
        )
        if not normalized_date:
            raise InvalidDateError(date_field, date)

        return cls(
            participant=ParticipantIdentification.from_form_record(record),
            date=normalized_date,
            visit=VisitIdentification.from_form_record(record),
            data=FormIdentification.from_form_record(record),
        )

    @classmethod
    def from_form_record_safe(
        cls, record: dict[str, Any], date_field: str
    ) -> Optional[Self]:
        """Creates object from form data record, returning None on error.

        This is a safe version of from_form_record that returns None instead of
        raising EmptyFieldError or InvalidDateError. Useful for error reporting
        where you want to include visit keys if available, but don't want to fail
        if they can't be extracted.

        Args:
          record: dictionary for record from form data
          date_field: name of the date field to use
        Returns:
          DataIdentification object if successful, None if date field is empty
          or invalid
        """
        try:
            return cls.from_form_record(record, date_field)
        except (EmptyFieldError, InvalidDateError):
            return None

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
            # Use from_visit_metadata to handle flat structure from file info
            return cls.from_visit_metadata(**visit_data)
        except (ValidationError, TypeError):
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


class EmptyFieldError(Exception):
    def __init__(self, fieldname: str) -> None:
        self.fieldname = fieldname


class InvalidDateError(Exception):
    def __init__(self, date_field: str, value: str) -> None:
        self.date_field = date_field
        self.value = value


# VisitKeys = DataIdentification
#   create_from -> from_form_record
# VisitMetadata = DataIdentification
# .  create -> from_visit_info
# ImageVisitMetadata = DataIdentification
