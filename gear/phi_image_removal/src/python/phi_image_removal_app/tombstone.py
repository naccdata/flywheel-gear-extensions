"""Tombstone record models and helpers for the PHI Image Removal gear.

Defines the JSON record written in place of a deleted PHI image file and
the helper that derives the tombstone filename from the original name.
"""

from pathlib import Path
from typing import Any

from flywheel import FileEntry
from pydantic import BaseModel, Field


def tombstone_filename(name: str) -> str:
    """Returns the tombstone filename for an original file name.

    Strips all extensions and appends ``.json`` (e.g. ``foo.dicom.zip`` ->
    ``foo.json``).

    Args:
        name: the original file name
    Returns:
        the tombstone file name
    """
    stem = Path(name).name.split(".", 1)[0]
    return f"{stem}.json"


class FileParents(BaseModel):
    """Container hierarchy of the original file."""

    group: str | None = None
    project: str | None = None
    subject: str | None = None
    session: str | None = None
    acquisition: str | None = None


class OriginalFileDetails(BaseModel):
    """Details captured about the deleted PHI image file."""

    name: str
    file_id: str | None = None
    size: int | None = None
    type: str | None = None
    mimetype: str | None = None
    modality: str | None = None
    classification: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    hash: str | None = None
    version: int | None = None
    created: str | None = None
    modified: str | None = None
    origin: dict[str, Any] | None = None
    info: dict[str, Any] | None = None
    parents: FileParents


class TombstoneMetadata(BaseModel):
    """Provenance of the removal recorded in the tombstone."""

    removed_by_gear: str
    gear_version: str | None = None
    removed_at: str
    reason: str


class TombstoneRecord(BaseModel):
    """The full tombstone written in place of the deleted file."""

    tombstone: TombstoneMetadata
    original_file: OriginalFileDetails


def _isoformat(value: Any) -> str | None:
    """Returns an ISO string for a datetime-like value, or None."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_tombstone(
    file: FileEntry,
    *,
    gear_name: str,
    gear_version: str | None,
    removed_at: str,
    reason: str,
) -> TombstoneRecord:
    """Builds a tombstone record from a Flywheel file entry.

    Attributes are read defensively since the SDK does not guarantee every
    field is populated on every file.

    Args:
        file: the file entry being tombstoned
        gear_name: name of this gear
        gear_version: version of this gear, if available
        removed_at: UTC ISO timestamp of the removal
        reason: why the file was removed (e.g. the confirming tag)
    Returns:
        the populated tombstone record
    """
    origin = getattr(file, "origin", None)
    origin_data = (
        {"type": getattr(origin, "type", None), "id": getattr(origin, "id", None)}
        if origin is not None
        else None
    )

    parents = getattr(file, "parents", None)
    file_parents = FileParents(
        group=getattr(parents, "group", None),
        project=getattr(parents, "project", None),
        subject=getattr(parents, "subject", None),
        session=getattr(parents, "session", None),
        acquisition=getattr(parents, "acquisition", None),
    )

    details = OriginalFileDetails(
        name=file.name,
        file_id=getattr(file, "file_id", None),
        size=getattr(file, "size", None),
        type=getattr(file, "type", None),
        mimetype=getattr(file, "mimetype", None),
        modality=getattr(file, "modality", None),
        classification=getattr(file, "classification", None),
        tags=list(file.tags or []),
        hash=getattr(file, "hash", None),
        version=getattr(file, "version", None),
        created=_isoformat(getattr(file, "created", None)),
        modified=_isoformat(getattr(file, "modified", None)),
        origin=origin_data,
        info=getattr(file, "info", None),
        parents=file_parents,
    )

    return TombstoneRecord(
        tombstone=TombstoneMetadata(
            removed_by_gear=gear_name,
            gear_version=gear_version,
            removed_at=removed_at,
            reason=reason,
        ),
        original_file=details,
    )
