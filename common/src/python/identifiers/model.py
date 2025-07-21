"""Defines the Identifier data class."""

from typing import List, Optional

from pydantic import BaseModel, Field, RootModel, field_validator

GUID_PATTERN = r"^[a-zA-Z0-9_]+$"
NACCID_PATTERN = r"^NACC\d{6}$"
PTID_PATTERN = r"^[!-~]{1,10}$"  # printable non-whitespace characters


class GUIDField(BaseModel):
    """Base model for models with guid."""

    guid: Optional[str] = Field(None, max_length=20, pattern=GUID_PATTERN)


class ADCIDField(BaseModel):
    """Base model for models with adcid."""

    adcid: int = Field(ge=0)


def clean_ptid(value: str) -> str:
    return value.strip().lstrip("0")


class CenterFields(ADCIDField):
    """Base model for models with center ids."""

    ptid: str = Field(max_length=10, pattern=PTID_PATTERN)

    @field_validator("ptid", mode="before")
    def clean_ptid(cls, value: str) -> str:
        return clean_ptid(value)


class NACCADCField(BaseModel):
    """Base model for models with naccadc."""

    naccadc: int = Field(ge=0)


class NACCIDField(BaseModel):
    """Base model for models with naccid."""

    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)


class OptionalNACCIDField(BaseModel):
    """Base model for models with optional naccid."""

    naccid: Optional[str] = Field(max_length=10, pattern=NACCID_PATTERN)


class IdentifierObject(CenterFields, GUIDField, NACCADCField, NACCIDField):
    """Response model for identifiers.

    Hides unconventional naming of fields and has NACCID as string.
    """


class IdentifierList(RootModel):
    """Class to allow serialization of lists of identifiers.

    Otherwise, basically acts like a list.
    """

    root: List[IdentifierObject]

    def __bool__(self) -> bool:
        return bool(self.root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item) -> IdentifierObject:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, identifier: IdentifierObject) -> None:
        """Appends the identifier to the list."""
        self.root.append(identifier)


class CenterIdentifiers(CenterFields):
    """Model for ADCID, PTID pair."""


class ParticipantIdentifiers(NACCIDField, GUIDField):
    """Model for participant identifiers."""

    center_identifiers: CenterIdentifiers
    aliases: Optional[List[str]]
