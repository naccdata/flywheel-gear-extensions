"""Defines the Identifier data class."""
from typing import List, Optional

from pydantic import BaseModel, Field, RootModel

GUID_PATTERN = r"^[a-zA-Z0-9]+$"
NACCID_PATTERN = r"^NACC\d{6}$"
PTID_PATTERN = r"^[a-zA-Z0-9-]{1,10}$"


class IdentifierObject(BaseModel):
    """Response model for identifiers.

    Hides unconventional naming of fields and has NACCID as string.
    """
    adcid: int = Field(ge=0)
    naccadc: int
    ptid: str = Field(max_length=10)
    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)
    guid: Optional[str] = Field(None, max_length=13, pattern=GUID_PATTERN)


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


class CenterIdentifiers(BaseModel):
    """Model for ADCID, PTID pair."""
    adcid: int = Field(ge=0)
    ptid: str = Field(max_length=10)


class ParticipantIdentifiers(BaseModel):
    """Model for participant identifiers."""
    center_identifiers: CenterIdentifiers
    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)
    aliases: Optional[List[str]]
    guid: Optional[str]
