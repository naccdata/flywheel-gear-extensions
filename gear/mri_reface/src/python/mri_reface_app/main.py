"""Runs mri_reface on a staged input and collects its outputs."""

import glob
import gzip
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

log = logging.getLogger(__name__)

# Exact launcher command; set it if auto-detection picks the wrong executable.
REFACE_COMMAND: str | None = None
CANDIDATE_EXES = ["run_mri_reface", "run_mri_reface.sh", "mri_reface"]
CANDIDATE_DIRS = ["/opt", "/usr/local", "/home", "/app", "/mri_reface"]

MCR_ENV_VARS = ["MCRROOT", "MCR_ROOT", "MATLAB_RUNTIME", "MCR_PATH"]
MCR_GLOBS = [
    "/opt/mcr/*",
    "/opt/matlab-runtime/*",
    "/opt/MATLAB/MATLAB_Runtime/*",
    "/usr/local/MATLAB/MATLAB_Runtime/*",
    "/opt/matlabruntime/*",
    "/opt/mcr",
]
MCR_ARG_MARKERS = ('MCRROOT="$1"', "MCRROOT=$1", "<deployedMCRroot>")

INPUT_EXTENSIONS = [
    (".nii.gz", "nifti_gz"),
    (".nii", "nifti"),
    (".dicom.zip", "zip"),
    (".dcm.zip", "zip"),
    (".zip", "zip"),
    (".dcm", "dcm"),
    (".dicom", "dcm"),
]
SKIPPED_ZIP_SUFFIXES = (".txt", ".json", ".xml")

# Registration by-products that mri_reface writes next to the refaced image.
TRANSFORM_PATTERN = re.compile(r"_to_MCALT_.*(Affine|Warp)", re.IGNORECASE)


class RefaceError(Exception):
    """Raised when mri_reface cannot be run or produces no refaced image."""


class RefaceConfig(BaseModel):
    """Gear options for the mri_reface run and its outputs."""

    im_type: str = ""
    gzip_nifti: bool = True
    save_transforms: bool = False
    extra_args: str = ""


class StagedInput(NamedTuple):
    """The input as mri_reface will read it."""

    path: Path
    stem: str
    kind: str


def split_name(filename: str) -> tuple[str, str | None]:
    """Returns the stem and kind (nifti, nifti_gz, zip, dcm, or None)."""
    lowered = filename.lower()
    for extension, kind in INPUT_EXTENSIONS:
        if lowered.endswith(extension):
            return filename[: -len(extension)], kind
    return Path(filename).stem, None


def safe_stem(stem: str) -> str:
    """Replaces periods and odd characters with dashes.

    mri_reface parses file names on periods.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")
    return cleaned or "input"


def find_mcr_root() -> str | None:
    """Returns the MATLAB Runtime root from the environment or common paths."""
    for var in MCR_ENV_VARS:
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            return value
    for pattern in MCR_GLOBS:
        for candidate in sorted(glob.glob(pattern)):
            if Path(candidate, "runtime", "glnxa64").is_dir():
                return candidate
    return None


def find_reface_executable() -> str:
    """Returns the path of the mri_reface launcher in the image."""
    for name in CANDIDATE_EXES:
        found = shutil.which(name)
        if found:
            return found
    for base in CANDIDATE_DIRS:
        for name in CANDIDATE_EXES:
            hits = [
                hit
                for hit in glob.glob(f"{base}/**/{name}", recursive=True)
                if os.access(hit, os.X_OK) and Path(hit).is_file()
            ]
            if hits:
                return min(hits, key=len)
    raise RefaceError(
        f"Could not find mri_reface in the image (looked for "
        f"{', '.join(CANDIDATE_EXES)}); set REFACE_COMMAND"
    )


def needs_mcr_root(executable: Path) -> bool:
    """Checks whether a MATLAB run_<app>.sh launcher takes the Runtime root."""
    name = executable.name
    if not (name.startswith("run_") and name.endswith(".sh")):
        return False
    try:
        text = executable.read_text(errors="ignore")
    except OSError:
        return False
    return any(marker in text for marker in MCR_ARG_MARKERS)


def find_reface_command() -> list[str]:
    """Returns the mri_reface launch command."""
    if REFACE_COMMAND:
        return shlex.split(REFACE_COMMAND)

    executable = find_reface_executable()
    if not needs_mcr_root(Path(executable)):
        return [executable]

    mcr_root = find_mcr_root()
    if not mcr_root:
        raise RefaceError(
            f"{executable} needs the MATLAB Runtime path, but none was found; "
            "set REFACE_COMMAND"
        )
    return [executable, mcr_root]


def is_skipped_zip_member(info: zipfile.ZipInfo) -> bool:
    """Flags directories, OS junk, and non-DICOM side files in a zip."""
    base = Path(info.filename).name
    lowered = base.lower()
    return (
        info.is_dir()
        or not base
        or base.startswith(".")
        or "__MACOSX" in info.filename
        or lowered == "dicomdir"
        or lowered.endswith(SKIPPED_ZIP_SUFFIXES)
    )


def extract_dicom_zip(source: Path, dicom_dir: Path) -> None:
    """Flattens a zipped DICOM series into numbered files in dicom_dir."""
    count = 0
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            if is_skipped_zip_member(info):
                continue
            count += 1
            base = safe_stem(Path(info.filename).name)
            target = dicom_dir / f"{count:05d}_{base}.dcm"
            with archive.open(info) as fin, target.open("wb") as fout:
                shutil.copyfileobj(fin, fout)
    log.info("Extracted %d DICOM files into a flat series directory", count)
    if count == 0:
        raise RefaceError("The zip contained no DICOM files")


def stage_input(source: Path, stage_dir: Path) -> StagedInput:
    """Copies the input into stage_dir in the form mri_reface reads."""
    stem, kind = split_name(source.name)
    stem = safe_stem(stem)
    stage_dir.mkdir(parents=True, exist_ok=True)

    if kind == "nifti":
        target = stage_dir / f"{stem}.nii"
        shutil.copyfile(source, target)
        return StagedInput(path=target, stem=stem, kind="nifti")

    if kind == "nifti_gz":
        target = stage_dir / f"{stem}.nii"
        with gzip.open(source, "rb") as fin, target.open("wb") as fout:
            shutil.copyfileobj(fin, fout)
        log.info("Decompressed .nii.gz (mri_reface needs uncompressed .nii)")
        return StagedInput(path=target, stem=stem, kind="nifti")

    if kind in ("zip", "dcm"):
        dicom_dir = stage_dir / stem
        dicom_dir.mkdir(parents=True, exist_ok=True)
        if kind == "dcm":
            shutil.copyfile(source, dicom_dir / source.name)
        else:
            extract_dicom_zip(source, dicom_dir)
        return StagedInput(path=dicom_dir, stem=stem, kind="dicom")

    raise RefaceError(
        f"Unsupported input '{source.name}'. "
        "Use .nii, .nii.gz, or a zip of one DICOM series."
    )


def is_dicom(path: Path) -> bool:
    """Checks for the DICM preamble marker."""
    try:
        with path.open("rb") as file:
            file.seek(128)
            return file.read(4) == b"DICM"
    except OSError:
        return False


def find_dicom_dirs(tool_out: Path) -> list[Path]:
    """Returns the directories holding DICOM files that mri_reface wrote."""
    return sorted(
        {
            path.parent
            for path in tool_out.rglob("*")
            if path.is_file() and is_dicom(path)
        }
    )


def zip_dicom_dirs(dicom_dirs: list[Path], output_dir: Path, stem: str) -> list[str]:
    """Zips each DICOM directory into a <stem>_deFaced.dicom.zip output."""
    saved = []
    for index, dicom_dir in enumerate(dicom_dirs):
        suffix = "" if len(dicom_dirs) == 1 else f"_{index + 1}"
        name = f"{stem}_deFaced{suffix}.dicom.zip"
        with zipfile.ZipFile(output_dir / name, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(dicom_dir.iterdir()):
                if path.is_file():
                    archive.write(path, arcname=f"{stem}_deFaced/{path.name}")
        saved.append(name)
    return saved


def copy_output_file(path: Path, output_dir: Path, config: RefaceConfig) -> str:
    """Copies one output file, gzipping a .nii when configured to."""
    if config.gzip_nifti and path.name.lower().endswith(".nii"):
        name = f"{path.name}.gz"
        with (
            path.open("rb") as fin,
            gzip.open(output_dir / name, "wb", compresslevel=6) as fout,
        ):
            shutil.copyfileobj(fin, fout)
        return name
    shutil.copyfile(path, output_dir / path.name)
    return path.name


def collect_outputs(
    tool_out: Path, output_dir: Path, stem: str, config: RefaceConfig
) -> list[str]:
    """Copies mri_reface results to output_dir and returns the saved names."""
    dicom_dirs = find_dicom_dirs(tool_out)
    saved = zip_dicom_dirs(dicom_dirs, output_dir, stem)
    for path in sorted(tool_out.rglob("*")):
        if not path.is_file() or path.parent in dicom_dirs:
            continue
        if TRANSFORM_PATTERN.search(path.name) and not config.save_transforms:
            log.debug("Skipping registration file %s", path.name)
            continue
        saved.append(copy_output_file(path, output_dir, config))
    return saved


def build_command(
    staged: StagedInput, tool_out: Path, config: RefaceConfig
) -> list[str]:
    """Builds the mri_reface command line for the staged input."""
    command = [*find_reface_command(), str(staged.path), str(tool_out)]
    im_type = config.im_type.strip()
    if im_type:
        command += ["-imType", im_type]
    elif staged.kind == "dicom":
        log.warning(
            "No im_type given; the author strongly recommends setting it "
            "for DICOM input"
        )
    if config.extra_args:
        command += shlex.split(config.extra_args)
    return command


def run(
    *, input_path: Path, work_dir: Path, output_dir: Path, config: RefaceConfig
) -> list[str]:
    """Refaces the input with mri_reface and returns the saved output names.

    Raises:
        RefaceError if mri_reface fails or produces no refaced image
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    staged = stage_input(input_path, work_dir / "in")
    tool_out = work_dir / "out"
    tool_out.mkdir(parents=True, exist_ok=True)

    command = build_command(staged, tool_out, config)
    log.info("Running: %s", shlex.join(command))
    log.debug("Environment:\n%s", json.dumps(dict(os.environ), indent=2))

    # mri_reface writes temp files to $TMPDIR; keep them in the job's work dir.
    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    result = subprocess.run(
        command,
        cwd=work_dir,
        env={**os.environ, "TMPDIR": str(tmp_dir)},
        check=False,
    )
    if result.returncode != 0:
        raise RefaceError(f"mri_reface exited with code {result.returncode}")

    produced = sorted(
        str(path.relative_to(tool_out))
        for path in tool_out.rglob("*")
        if path.is_file()
    )
    log.debug("mri_reface produced: %s", produced)
    if not any("deFaced" in name or "refaced" in name.lower() for name in produced):
        raise RefaceError(
            "mri_reface finished but no refaced image was found in its output: "
            f"{produced}"
        )

    saved = collect_outputs(tool_out, output_dir, staged.stem, config)
    log.info("Saved %d output file(s): %s", len(saved), ", ".join(saved))
    return saved
