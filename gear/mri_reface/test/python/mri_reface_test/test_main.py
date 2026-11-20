"""Tests for the MRI Reface staging and output handling."""

import gzip
import zipfile
from pathlib import Path

import pytest

from mri_reface_app import main
from mri_reface_app.main import (
    RefaceConfig,
    RefaceError,
    StagedInput,
    build_command,
    collect_outputs,
    safe_stem,
    split_name,
    stage_input,
)


def write_dicom(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * 128 + b"DICM" + b"payload")


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("T1.nii.gz", ("T1", "nifti_gz")),
        ("T1.NII", ("T1", "nifti")),
        ("scan.dicom.zip", ("scan", "zip")),
        ("scan.zip", ("scan", "zip")),
        ("slice.dcm", ("slice", "dcm")),
        ("notes.txt", ("notes", None)),
    ],
)
def test_split_name(filename: str, expected: tuple[str, str | None]) -> None:
    assert split_name(filename) == expected


def test_safe_stem() -> None:
    assert safe_stem("sub 01.T1w.v2") == "sub-01-T1w-v2"
    assert safe_stem("...") == "input"


def test_stage_nifti_gz(tmp_path: Path) -> None:
    source = tmp_path / "sub.01.nii.gz"
    with gzip.open(source, "wb") as file:
        file.write(b"nifti-bytes")

    staged = stage_input(source, tmp_path / "in")

    assert staged.kind == "nifti"
    assert staged.stem == "sub-01"
    assert staged.path.name == "sub-01.nii"
    assert staged.path.read_bytes() == b"nifti-bytes"


def test_stage_dicom_zip_skips_junk(tmp_path: Path) -> None:
    source = tmp_path / "series.dicom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("series/IM0001", b"a")
        archive.writestr("series/IM0002", b"b")
        archive.writestr("series/.DS_Store", b"x")
        archive.writestr("__MACOSX/series/._IM0001", b"x")
        archive.writestr("series/DICOMDIR", b"x")
        archive.writestr("series/readme.txt", b"x")

    staged = stage_input(source, tmp_path / "in")

    assert staged.kind == "dicom"
    assert sorted(path.name for path in staged.path.iterdir()) == [
        "00001_IM0001.dcm",
        "00002_IM0002.dcm",
    ]


def test_stage_empty_zip_raises(tmp_path: Path) -> None:
    source = tmp_path / "empty.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("notes.txt", b"x")

    with pytest.raises(RefaceError):
        stage_input(source, tmp_path / "in")


def test_stage_unsupported_raises(tmp_path: Path) -> None:
    source = tmp_path / "scan.mgz"
    source.write_bytes(b"x")

    with pytest.raises(RefaceError):
        stage_input(source, tmp_path / "in")


def test_collect_outputs(tmp_path: Path) -> None:
    tool_out = tmp_path / "out"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    write_dicom(tool_out / "dicom" / "0001.dcm")
    write_dicom(tool_out / "dicom" / "0002.dcm")
    (tool_out / "T1_deFaced.nii").write_bytes(b"refaced")
    (tool_out / "T1_deFaced.png").write_bytes(b"render")
    (tool_out / "T1_to_MCALT_0GenericAffine.txt").write_text("affine")

    saved = collect_outputs(tool_out, output_dir, "T1", RefaceConfig())

    assert sorted(saved) == [
        "T1_deFaced.dicom.zip",
        "T1_deFaced.nii.gz",
        "T1_deFaced.png",
    ]
    with gzip.open(output_dir / "T1_deFaced.nii.gz", "rb") as file:
        assert file.read() == b"refaced"
    with zipfile.ZipFile(output_dir / "T1_deFaced.dicom.zip") as archive:
        assert sorted(archive.namelist()) == [
            "T1_deFaced/0001.dcm",
            "T1_deFaced/0002.dcm",
        ]


def test_collect_outputs_keeps_transforms(tmp_path: Path) -> None:
    tool_out = tmp_path / "out"
    output_dir = tmp_path / "output"
    tool_out.mkdir()
    output_dir.mkdir()
    (tool_out / "T1_deFaced.nii").write_bytes(b"refaced")
    (tool_out / "T1_to_MCALT_0GenericAffine.txt").write_text("affine")

    saved = collect_outputs(
        tool_out,
        output_dir,
        "T1",
        RefaceConfig(gzip_nifti=False, save_transforms=True),
    )

    assert sorted(saved) == ["T1_deFaced.nii", "T1_to_MCALT_0GenericAffine.txt"]


def test_build_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "REFACE_COMMAND", "/opt/run_mri_reface.sh /opt/mcr")
    staged = StagedInput(path=tmp_path / "T1.nii", stem="T1", kind="nifti")
    config = RefaceConfig(im_type=" T1 ", extra_args="-someFlag 'a b'")

    command = build_command(staged, tmp_path / "out", config)

    assert command == [
        "/opt/run_mri_reface.sh",
        "/opt/mcr",
        str(tmp_path / "T1.nii"),
        str(tmp_path / "out"),
        "-imType",
        "T1",
        "-someFlag",
        "a b",
    ]
