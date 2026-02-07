from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional

from flywheel.models.file_entry import FileEntry
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
)

from nacc_common.field_names import FieldNames


class QCVisitor(ABC):
    """Abstract base class for QC visitors."""

    @abstractmethod
    def visit_file_model(self, file_model: "FileQCModel") -> None:
        """Applies this visitor to the file model.

        Args:
          file_model: the model to visit
        """

    @abstractmethod
    def visit_gear_model(self, gear_model: "GearQCModel") -> None:
        """Applies this method to the gear model.

        Args:
          gear_model: the model to visit
        """

    @abstractmethod
    def visit_validation_model(self, validation_model: "ValidationModel") -> None:
        """Applies this visitor to the validation model.

        Args:
          validation_model: the model to visit
        """

    @abstractmethod
    def visit_file_error(self, file_error: "FileError") -> None:
        """Applies this visitor to the file error model.

        Args:
          file_error: the model to visit
        """

    @abstractmethod
    def visit_cleared_alert(self, cleared_alert: "ClearedAlertModel") -> None:
        """Applies this visitor to the cleared alert model.

        Args:
          cleared_alert: the model to visit
        """

    @abstractmethod
    def visit_alert_provenance(
        self, alert_provenance: "ClearedAlertProvenance"
    ) -> None:
        """Applies this visitor to the cleared alert provenance model.

        Args:
          alert_provenance: the model to visit
        """


class CSVLocation(BaseModel):
    """Represents location of an error in a CSV file."""

    model_config = ConfigDict(populate_by_name=True)

    line: int
    column_name: str


class JSONLocation(BaseModel):
    """Represents the location of an error in a JSON file."""

    model_config = ConfigDict(populate_by_name=True)

    key_path: str


class VisitKeys(BaseModel):
    adcid: Optional[int] = None
    ptid: Optional[str] = None
    visitnum: Optional[str] = None
    module: Optional[str] = None
    date: Optional[str] = None
    naccid: Optional[str] = None

    @classmethod
    def create_from(
        cls, record: Dict[str, Any], date_field: Optional[str] = None
    ) -> "VisitKeys":
        date = record.get(date_field) if date_field is not None else None
        return VisitKeys(
            adcid=record.get(FieldNames.ADCID),
            ptid=record.get(FieldNames.PTID),
            visitnum=record.get(FieldNames.VISITNUM),
            date=date,
            naccid=record.get(FieldNames.NACCID),
            module=record.get(FieldNames.MODULE),
        )


class VisitMetadata(VisitKeys):
    """Extended visit metadata that includes packet information for VisitEvent
    creation.

    Extends VisitKeys with the packet field needed for form events. Only
    includes fields actually needed for VisitEvent creation.
    """

    packet: Optional[str] = None

    @model_serializer(mode="wrap")
    def to_visit_event_fields(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> Dict[str, Any]:
        """Extract fields needed for VisitEvent creation. with proper field
        name mapping.

        Returns:
            Dictionary with fields mapped to VisitEvent field names
        """
        # Use model_dump and map field names for VisitEvent
        data = handler(self)
        if info.mode == "raw":
            return data

        # Map field names, handling cases where keys might not exist
        # (e.g., when exclude_none=True and the value is None)
        if "date" in data:
            data["visit_date"] = data.pop("date")
        if "visitnum" in data:
            data["visit_number"] = data.pop("visitnum")
        return data

    @classmethod
    def create(cls, file_entry: FileEntry) -> Optional["VisitMetadata"]:
        """Factory method to create VisitMetadata from a FileEntry.

        Args:
          file_entry: the file entry
        Returns:
          the VisitMetadata instance if there is visit metadata. None, otherwise.
        """
        file_entry = file_entry.reload()
        if not file_entry.info:
            return None

        visit_data = file_entry.info.get("visit")
        if not visit_data:
            return None

        try:
            return VisitMetadata.model_validate(visit_data)
        except ValidationError:
            return None


class FileError(BaseModel):
    """Represents an error that might be found in file during a step in a
    pipeline."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: Optional[str] = None
    error_type: Literal["alert", "error", "warning"] = Field(alias="type")
    error_code: str = Field(alias="code")
    location: Optional[CSVLocation | JSONLocation] = None
    container_id: Optional[str] = None
    flywheel_path: Optional[str] = None
    value: Optional[str] = None
    expected: Optional[str] = None
    message: str
    ptid: Optional[str] = None
    visitnum: Optional[str] = None
    date: Optional[str] = None
    naccid: Optional[str] = None

    @classmethod
    def fieldnames(cls) -> List[str]:
        """Gathers the serialized field names for the class."""
        result: list[str] = []
        for fieldname, field_info in cls.model_fields.items():
            if field_info.serialization_alias:
                result.append(field_info.serialization_alias)
            else:
                result.append(fieldname)
        return result

    def apply(self, visitor: QCVisitor) -> None:
        visitor.visit_file_error(self)


class FileErrorList(RootModel):
    """Serialization model for lists of FileError."""

    root: List[FileError]

    def __bool__(self) -> bool:
        return bool(self.root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> FileError:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def clear(self):
        self.root.clear()

    def append(self, error: FileError) -> None:
        """Appends the error to the list."""
        self.root.append(error)

    def list(self) -> List[FileError]:
        return self.root


QCStatus = Literal["PASS", "FAIL", "IN REVIEW"]

# QC Status constants
QC_STATUS_PASS = "PASS"
QC_STATUS_FAIL = "FAIL"
QC_STATUS_IN_REVIEW = "IN REVIEW"


class GearTags:
    def __init__(self, gear_name: str):
        self.__gear_name = gear_name

    @property
    def pass_tag(self) -> str:
        return f"{self.__gear_name}-PASS"

    @property
    def fail_tag(self) -> str:
        return f"{self.__gear_name}-FAIL"

    def get_status_tag(self, status: str) -> str:
        return f"{self.__gear_name}-{status}"

    def update_tags(self, tags: List[str], status: str) -> List[str]:
        """Update the list of tags with current status for the gear.

        Args:
            tags: list of existing tags
            status: gear job status (PASS/FAIL)

        Returns:
            List[str]: list of updated tags
        """

        if not tags:
            tags = []

        if self.fail_tag in tags:
            tags.remove(self.fail_tag)
        if self.pass_tag in tags:
            tags.remove(self.pass_tag)

        tags.append(self.get_status_tag(status=status))

        return tags


class ClearedAlertProvenance(BaseModel):
    """Model for provenance of alert clearance."""

    user: str
    clear_set_to: bool = Field(alias="clearSetTo")
    timestamp: str

    def apply(self, visitor: QCVisitor) -> None:
        visitor.visit_alert_provenance(self)


class ClearedAlertModel(BaseModel):
    """Model for cleared alert."""

    clear: bool
    finalized: bool
    provenance: List[ClearedAlertProvenance]
    alert_hash: str = Field(alias="alertHash")

    def apply(self, visitor: QCVisitor) -> None:
        visitor.visit_cleared_alert(self)


class ValidationModel(BaseModel):
    """Model for the validation data for a gear run.

    Located within file.info.qc.<gear-name>.validation.
    """

    data: List[FileError] = Field([])
    cleared: Optional[List[ClearedAlertModel]] = Field([])
    state: Optional[QCStatus] = Field(None)

    def extend(self, errors: List[FileError]) -> None:
        self.data.extend(errors)

    def apply(self, visitor: QCVisitor) -> None:
        visitor.visit_validation_model(self)


class GearQCModel(BaseModel):
    """Model for the FW Job QC gear object in file.info.qc.

    Note: also has job_info.
    """

    validation: ValidationModel

    def get_status(self) -> Optional[QCStatus]:
        return self.validation.state

    def get_errors(self) -> List[FileError]:
        return self.validation.data

    def set_errors(self, errors: List[FileError]) -> None:
        self.validation.data = errors

    def set_status(self, state: QCStatus) -> None:
        self.validation.state = state

    def reset_cleared_alerts(self) -> None:
        self.validation.cleared = []

    def apply(self, visitor: QCVisitor):
        visitor.visit_gear_model(self)


class FileQCModel(BaseModel):
    """Model for the FW Job QC object at file.info.

    Object at file.info is created by
    GearContext.metadata.add_qc_result.
    """

    qc: Dict[str, GearQCModel]

    @classmethod
    def create(cls, file_entry: FileEntry) -> "FileQCModel":
        """Factory method to create FileQCModel from a FileEntry.

        Args:
            file_entry: The file entry to extract QC info from

        Returns:
            FileQCModel instance

        Raises:
            ValidationError: If the file.info structure is invalid
        """
        file_entry = file_entry.reload()
        if not file_entry.info:
            return cls(qc={})
        if "qc" not in file_entry.info:
            return cls(qc={})

        return cls.model_validate(file_entry.info, by_alias=True)

    def get(self, gear_name: str) -> Optional[GearQCModel]:
        return self.qc.get(gear_name)

    def reset(self, gear_name: str) -> None:
        if gear_name in self.qc:
            self.qc.pop(gear_name)

    def set(self, gear_name: str, gear_model: GearQCModel) -> None:
        self.qc[gear_name] = gear_model

    def get_status(self, gear_name: str) -> Optional[QCStatus]:
        """Returns the QC status for the named gear.

        Args:
          gear_name: the name of the gear
        Returns: the status from the validation model of the gear. None, if none exists.
        """
        gear_model = self.get(gear_name)
        if gear_model is None:
            return None
        return gear_model.get_status()

    def get_errors(self, gear_name: str) -> List[FileError]:
        gear_model = self.get(gear_name)
        if gear_model is None:
            return []

        return gear_model.get_errors()

    def set_errors(
        self,
        gear_name: str,
        status: QCStatus,
        errors: List[FileError] | FileErrorList,
        reset_cleared: Optional[bool] = True,
    ) -> None:
        """Sets the status and errors in the validation model for the gear.

        Args:
          gear_name: the name of the gear
          status: the QC status to set
          errors: the list of errors to set
          reset_cleared (optional): reset cleared alerts (Default True)
        """
        if isinstance(errors, FileErrorList):
            errors = errors.list()

        gear_model = self.get(gear_name)
        if gear_model is None:
            self.qc[gear_name] = GearQCModel(
                validation=ValidationModel(data=errors, state=status, cleared=[])
            )
            return

        gear_model.set_errors(errors)
        gear_model.set_status(status)

        if reset_cleared:
            gear_model.reset_cleared_alerts()

    def get_file_status(self) -> QCStatus:
        """Returns the overall QC status for the file based on all gears.

        Returns:
          - "PASS" if all gears have status "PASS"
          - "FAIL" if any gear has status "FAIL"
          - "IN REVIEW" if no gear has status "FAIL" and at least one
            gear has status "IN REVIEW"
        """
        status_set = {gear_model.get_status() for gear_model in self.qc.values()}
        if "FAIL" in status_set:
            return "FAIL"

        if "IN REVIEW" in status_set:
            return "IN REVIEW"

        return "PASS"

    def apply(self, visitor: QCVisitor):
        visitor.visit_file_model(self)
