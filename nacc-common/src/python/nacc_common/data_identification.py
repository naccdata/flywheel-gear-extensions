from abc import ABC, abstractmethod
from typing import Any, Optional, Self

from dates.form_dates import DEFAULT_DATE_FORMAT, convert_date
from identifiers.model import PTID_PATTERN
from pydantic import (
    BaseModel,
    Field,
    ModelWrapValidatorHandler,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from nacc_common.field_names import FieldNames


class AbstractIdentificationVisitor(ABC):
    """Abstract visitor for traversing identification components."""

    @abstractmethod
    def visit_participant(self, participant: "ParticipantIdentification") -> None:
        """Visit a ParticipantIdentification component."""
        pass

    @abstractmethod
    def visit_visit(self, visit: "VisitIdentification") -> None:
        """Visit a VisitIdentification component."""
        pass

    @abstractmethod
    def visit_form(self, form: "FormIdentification") -> None:
        """Visit a FormIdentification component."""
        pass

    @abstractmethod
    def visit_image(self, image: "ImageIdentification") -> None:
        """Visit an ImageIdentification component."""
        pass

    @abstractmethod
    def visit_data_identification(self, data_id: "DataIdentification") -> None:
        """Visit a DataIdentification component."""
        pass


class ParticipantIdentification(BaseModel):
    """Identifies a participant and their center."""

    adcid: Optional[int] = None
    ptid: str
    naccid: Optional[str] = None

    @field_validator("ptid")
    @classmethod
    def normalize_ptid(cls, value: str) -> str:
        return value.strip().lstrip("0")

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

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this participant identification."""
        visitor.visit_participant(self)


class VisitIdentification(BaseModel):
    """Identifies a specific visit.

    If this object exists, visitnum must be present. Use visit=None at
    the DataIdentification level for non-visit data.
    """

    visitnum: str

    @classmethod
    def from_form_record(cls, record: dict[str, Any]) -> Optional[Self]:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          VisitIdentification if visitnum is present, None otherwise
        """
        visitnum = record.get(FieldNames.VISITNUM)
        # Convert empty string to None
        if visitnum == "" or visitnum is None:
            return None
        return cls(visitnum=visitnum)

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this visit identification."""
        visitor.visit_visit(self)


class FormIdentification(BaseModel):
    """Identifies form-specific data.

    If this object exists, module must be present. Packet is optional as
    not all forms have packets.
    """

    module: str  # Form name (A1, B1, NP, Milestone, etc.) - required
    packet: Optional[str] = None  # I=Initial, F=Followup, T=Telephone - optional

    @classmethod
    def from_form_record(cls, record: dict[str, Any]) -> Self:
        """Creates object from form data record.

        Args:
          record: dictionary for record from form data
        Returns:
          object created from record
        Raises:
          EmptyFieldError if module is missing
        """
        module = record.get(FieldNames.MODULE)
        if module is None:
            raise EmptyFieldError(FieldNames.MODULE)

        packet = record.get(FieldNames.PACKET)
        # Convert empty string to None
        if packet == "":
            packet = None

        return cls(module=module, packet=packet)

    @field_validator("module")
    @classmethod
    def normalize_module(cls, v: str) -> str:
        """Normalize module to uppercase for canonical storage and matching.

        This ensures consistency with EventMatchKey matching logic and
        provides case-insensitive module handling throughout the system.

        Args:
            v: The module value

        Returns:
            Module normalized to uppercase
        """
        return v.upper()

    @field_validator("packet")
    @classmethod
    def normalize_packet(cls, v: Optional[str]) -> Optional[str]:
        """Normalize packet to uppercase for canonical storage and matching.

        Args:
            v: The packet value

        Returns:
            Packet normalized to uppercase, or None if input is None
        """
        return v.upper() if v else v

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this form identification."""
        visitor.visit_form(self)


class ImageIdentification(BaseModel):
    """Identifies image-specific data.

    If this object exists, modality must be present.
    """

    modality: str  # Imaging modality (MR, CT, PET, etc.) - required

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this image identification."""
        visitor.visit_image(self)


class DataIdentification(BaseModel):
    """Base class for all data identification using composition.

    Combines participant identification with optional visit
    identification. This replaces the legacy VisitKeys class.

    Required fields:
    - participant: Always required
    - date: Always required (data always has a date)
    - data: Always required (FormIdentification or ImageIdentification)

    Optional fields (use None when not applicable):
    - visit: None for non-visit data (e.g., enrollment, milestones)
    """

    participant: ParticipantIdentification
    date: str
    visit: Optional[VisitIdentification] = None
    data: FormIdentification | ImageIdentification

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
            ptid: Participant identifier (center-assigned) - required
            naccid: Participant identifier (NACC-assigned)
            visitnum: Visit sequence number
            date: Visit date or collection date - required
            module: Form name - required unless modality is provided
            packet: Form packet (I/F/T)
            modality: Imaging modality - required unless module is provided

        Returns:
            DataIdentification with composed structure

        Raises:
            ValidationError if required fields (ptid, date, module/modality) are missing
        """
        participant = ParticipantIdentification(
            adcid=adcid,
            ptid=ptid,
            naccid=naccid,
        )

        # Create visit object only if visitnum is present
        visit = VisitIdentification(visitnum=visitnum) if visitnum else None

        # Create data object - either form or image (required)
        data: FormIdentification | ImageIdentification
        if modality is not None:
            data = ImageIdentification(modality=modality)
        elif module is not None:
            data = FormIdentification(module=module, packet=packet)
        else:
            raise ValueError("Either module or modality must be provided")

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
                # Cannot create FormIdentification with just packet - module is required
                # This is a limitation of the new design
                raise ValueError(
                    "Cannot add packet: FormIdentification requires module"
                )

        return self.model_copy(update=updates)

    def __getattr__(self, attribute_name: str) -> Optional[Any]:
        # Check participant
        if hasattr(self.participant, attribute_name):
            return getattr(self.participant, attribute_name)

        # Check visit (may be None)
        if self.visit is not None and hasattr(self.visit, attribute_name):
            return getattr(self.visit, attribute_name)

        # Return None for visitnum if visit is None (backward compatibility)
        if attribute_name == "visitnum" and self.visit is None:
            return None

        # Check data (always present)
        if hasattr(self.data, attribute_name):
            return getattr(self.data, attribute_name)

        raise AttributeError(
            f"No attribute {attribute_name} for DataIdentification object"
        )

    @model_validator(mode="wrap")
    @classmethod
    def visit_validator(
        cls, value: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """Ensure visit is None if visitnum would be None.

        This prevents creating VisitIdentification(visitnum=None) which
        is invalid.
        """
        if isinstance(value, DataIdentification):
            return handler(value)

        if isinstance(value, dict):
            visit = value.get("visit")
            # If visit is an object with visitnum=None, remove it
            if (isinstance(visit, dict) and visit.get("visitnum") is None) or (
                isinstance(visit, VisitIdentification) and visit.visitnum is None
            ):
                value = value.copy()  # Don't mutate the input
                value["visit"] = None

        return handler(value)

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
                # For visit, add visitnum=None to maintain backward compatibility
                if field_name == "visit":
                    data["visitnum"] = None
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

    def apply(self, visitor: AbstractIdentificationVisitor) -> None:
        """Apply visitor to this data identification and all its components."""
        visitor.visit_data_identification(self)
        self.participant.apply(visitor)
        if self.visit is not None:
            self.visit.apply(visitor)
        self.data.apply(visitor)


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
