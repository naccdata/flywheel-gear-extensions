from typing import List, Literal, Optional

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
    error_type: Literal["alert", "error", "warning"] = Field(serialization_alias="type")
    error_code: str = Field(serialization_alias="code")
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
