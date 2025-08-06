from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel


class CSVLocation(BaseModel):
    """Represents location of an error in a CSV file."""

    model_config = ConfigDict(populate_by_name=True)

    line: int
    column_name: str


class JSONLocation(BaseModel):
    """Represents the location of an error in a JSON file."""

    model_config = ConfigDict(populate_by_name=True)

    key_path: str


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

    @classmethod
    def fieldnames(cls) -> List[str]:
        """Gathers the serialized field names for the class."""
        result = []
        for fieldname, field_info in cls.model_fields.items():
            if field_info.serialization_alias:
                result.append(field_info.serialization_alias)
            else:
                result.append(fieldname)
        return result


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


QCStatus = Literal["PASS", "FAIL"]


class ClearedAlertProvenance(BaseModel):
    """Model for provenance of alert clearance."""

    user: str
    clear_set_to: bool = Field(alias="clearSetTo")
    timestamp: str


class ClearedAlertModel(BaseModel):
    """Model for cleared alert."""

    clear: bool
    finalized: bool
    provenance: List[ClearedAlertProvenance]
    alert_hash: str = Field(alias="alertHash")


class ValidationModel(BaseModel):
    """Model for the validation data for a gear run.

    Located within file.info.qc.<gear-name>.validation.
    """

    data: List[FileError] = Field([])
    cleared: Optional[List[ClearedAlertModel]] = Field([])
    state: Optional[QCStatus] = Field(None)

    def extend(self, errors: List[FileError]) -> None:
        self.data.extend(errors)


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


class FileQCModel(BaseModel):
    """Model for the FW Job QC object at file.info.

    Object at file.info is created by
    GearToolkitContext.metadata.add_qc_result.
    """

    qc: Dict[str, GearQCModel]

    def get(self, gear_name: str) -> Optional[GearQCModel]:
        return self.qc.get(gear_name)

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
        self, gear_name: str, status: QCStatus, errors: List[FileError] | FileErrorList
    ) -> None:
        """Sets the status and errors in the validation model for the gear.

        Args:
          gear_name: the name of the gear
          status: the QC status to set
          errors: the list of errors to set
        """
        if isinstance(errors, FileErrorList):
            errors = errors.list()

        gear_model = self.qc.get(gear_name)
        if gear_model is None:
            self.qc[gear_name] = GearQCModel(
                validation=ValidationModel(
                    data=errors, state=status, cleared=[])
            )
            return

        gear_model.set_errors(errors)
        gear_model.set_status(status)
