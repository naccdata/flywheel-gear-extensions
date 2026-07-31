"""Unit tests for tombstone filename and record building."""

import json
from types import SimpleNamespace

from phi_image_removal_app.tombstone import build_tombstone, tombstone_filename


def make_file() -> SimpleNamespace:
    return SimpleNamespace(
        name="NACC900026_MR.dicom.zip",
        tags=["PHI-Confirmed", "image-pii-detector"],
        file_id="file1",
        size=2048,
        type="dicom",
        mimetype="application/zip",
        modality="MR",
        classification={"Intent": ["Structural"]},
        hash="deadbeef",
        version=3,
        created=None,
        modified=None,
        origin=SimpleNamespace(type="user", id="user@example.org"),
        info={"qc": {"state": "PASS"}},
        parents=SimpleNamespace(
            group="g1",
            project="p1",
            subject="s1",
            session="ses1",
            acquisition="acq1",
        ),
    )


def test_tombstone_filename_strips_all_extensions() -> None:
    assert tombstone_filename("NACC900026_MR.dicom.zip") == "NACC900026_MR.json"
    assert tombstone_filename("plain.txt") == "plain.json"
    assert tombstone_filename("noext") == "noext.json"
    assert tombstone_filename("dir/sub/foo.dcm") == "foo.json"


def test_build_tombstone_captures_fields() -> None:
    record = build_tombstone(
        make_file(),  # type: ignore[arg-type]
        gear_name="phi-image-removal",
        gear_version="0.0.1",
        removed_at="2026-06-26T12:00:00+00:00",
        reason="PHI-Confirmed",
    )

    assert record.tombstone.removed_by_gear == "phi-image-removal"
    assert record.tombstone.gear_version == "0.0.1"
    assert record.tombstone.removed_at == "2026-06-26T12:00:00+00:00"
    assert record.tombstone.reason == "PHI-Confirmed"

    original = record.original_file
    assert original.name == "NACC900026_MR.dicom.zip"
    assert original.file_id == "file1"
    assert original.size == 2048
    assert original.modality == "MR"
    assert original.tags == ["PHI-Confirmed", "image-pii-detector"]
    assert original.origin == {"type": "user", "id": "user@example.org"}
    assert original.parents.acquisition == "acq1"


def test_build_tombstone_serializes_to_json() -> None:
    record = build_tombstone(
        make_file(),  # type: ignore[arg-type]
        gear_name="phi-image-removal",
        gear_version="0.0.1",
        removed_at="2026-06-26T12:00:00+00:00",
        reason="PHI-Confirmed",
    )

    data = json.loads(record.model_dump_json())
    assert data["original_file"]["name"] == "NACC900026_MR.dicom.zip"
    assert data["tombstone"]["reason"] == "PHI-Confirmed"
