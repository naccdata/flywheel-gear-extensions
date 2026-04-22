"""File resolution utilities for handling DICOM files and zip archives.

This module provides utilities for resolving input files that may be
either raw DICOM files or zip archives containing DICOM files. When a
zip archive is provided, it extracts the first DICOM file to a temporary
location.
"""

import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class FileResolverError(Exception):
    """Exception raised when file resolution fails."""


def resolve_dicom_file(
    file_path: Path,
) -> tuple[Path, Optional[tempfile.TemporaryDirectory]]:
    """Resolve an input file to a DICOM file path.

    If the input is a zip archive, extracts the first DICOM file to a
    temporary directory. If the input is a regular file, returns it
    directly.

    Args:
        file_path: Path to the input file (DICOM or zip archive)

    Returns:
        Tuple of (resolved_dicom_path, temp_dir). The temp_dir is None
        if no extraction was needed, otherwise it is a
        TemporaryDirectory that must be kept alive while the DICOM file
        is in use. The caller should use this in a context manager or
        call cleanup() when done.

    Raises:
        FileResolverError: If the zip contains no DICOM files or
            extraction fails
    """
    if not zipfile.is_zipfile(file_path):
        log.info(f"Input file is a regular DICOM file: {file_path.name}")
        return file_path, None

    log.info(f"Input file is a zip archive: {file_path.name}")
    return _extract_dicom_from_zip(file_path)


def _extract_dicom_from_zip(
    zip_path: Path,
) -> tuple[Path, tempfile.TemporaryDirectory]:
    """Extract the first DICOM file from a zip archive.

    Searches for files with common DICOM extensions (.dcm, .dicom) or
    files without extensions (common for DICOM). Extracts the first
    match to a temporary directory.

    Args:
        zip_path: Path to the zip archive

    Returns:
        Tuple of (extracted_dicom_path, temp_dir)

    Raises:
        FileResolverError: If no DICOM files found in the archive or
            extraction fails
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            dicom_entry = _find_dicom_entry(zf)

            if not dicom_entry:
                raise FileResolverError(
                    f"No DICOM files found in zip archive: {zip_path.name}. "
                    "Expected files with .dcm or .dicom extension, or files "
                    "without extensions."
                )

            temp_dir = tempfile.TemporaryDirectory()
            try:
                extracted_path = Path(zf.extract(dicom_entry, temp_dir.name))
                log.info(
                    f"Extracted DICOM file '{dicom_entry}' from "
                    f"zip archive to {extracted_path}"
                )
                return extracted_path, temp_dir
            except Exception:
                temp_dir.cleanup()
                raise

    except zipfile.BadZipFile as error:
        raise FileResolverError(
            f"Failed to read zip archive: {zip_path.name}. Error: {error}"
        ) from error


def _find_dicom_entry(zf: zipfile.ZipFile) -> Optional[str]:
    """Find the first DICOM file entry in a zip archive.

    Searches by extension (.dcm, .dicom) first, then falls back to
    files without extensions (common for DICOM files).

    Args:
        zf: Open ZipFile object

    Returns:
        Name of the first DICOM entry, or None if not found
    """
    dicom_extensions = {".dcm", ".dicom"}

    # First pass: look for files with DICOM extensions
    for name in zf.namelist():
        if _is_directory_entry(name):
            continue
        suffix = Path(name).suffix.lower()
        if suffix in dicom_extensions:
            return name

    # Second pass: look for files without extensions (common for DICOM)
    for name in zf.namelist():
        if _is_directory_entry(name):
            continue
        if not Path(name).suffix:
            return name

    return None


def _is_directory_entry(name: str) -> bool:
    """Check if a zip entry is a directory."""
    return name.endswith("/")
