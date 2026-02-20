"""DICOM parsing utilities for the Image Identifier Lookup gear.

This module provides utilities for reading DICOM tags from image files
using pydicom.
"""

from pathlib import Path
from typing import Optional

import pydicom


class InvalidDicomError(Exception):
    """Exception raised when a file is not a valid DICOM file or cannot be
    parsed."""


def read_dicom_tags(
    file_path: Path, tags: dict[str, tuple[int, int]]
) -> dict[str, Optional[str]]:
    """Read multiple DICOM tag values from file in a single read operation.

    Args:
        file_path: Path to DICOM file
        tags: Dictionary mapping field names to DICOM tags
              e.g., {"patient_id": (0x0010, 0x0020), "study_date": (0x0008, 0x0020)}

    Returns:
        Dictionary mapping field names to tag values (None if tag not found)

    Raises:
        InvalidDicomError: If file is not a valid DICOM file or cannot be parsed

    Examples:
        >>> tags = {
        ...     "patient_id": (0x0010, 0x0020),
        ...     "study_date": (0x0008, 0x0020),
        ...     "modality": (0x0008, 0x0060)
        ... }
        >>> result = read_dicom_tags(Path("image.dcm"), tags)
        >>> print(result["patient_id"])
    """
    try:
        # Read DICOM file once, stopping before pixel data for efficiency
        dcm = pydicom.dcmread(str(file_path), stop_before_pixels=True)

        result = {}
        for field_name, tag in tags.items():
            if tag in dcm:
                value = dcm[tag].value
                # Convert value to string, handling various DICOM value types
                result[field_name] = str(value) if value is not None else None
            else:
                result[field_name] = None

        return result

    except FileNotFoundError as error:
        raise InvalidDicomError(f"DICOM file not found: {file_path}") from error

    except pydicom.errors.InvalidDicomError as error:
        raise InvalidDicomError(
            f"Invalid DICOM file: {file_path}. Error: {error}"
        ) from error

    except (OSError, ValueError) as error:
        raise InvalidDicomError(
            f"Failed to read DICOM file: {file_path}. Error: {error}"
        ) from error


def read_dicom_tag(file_path: Path, tag: tuple[int, int]) -> Optional[str]:
    """Read a single DICOM tag value from file.

    Note: For reading multiple tags, use read_dicom_tags() instead to avoid
    reading the file multiple times.

    Args:
        file_path: Path to DICOM file
        tag: DICOM tag as tuple (group, element), e.g., (0x0010, 0x0020)

    Returns:
        Tag value as string, or None if tag not found

    Raises:
        InvalidDicomError: If file is not a valid DICOM file or cannot be parsed

    Examples:
        >>> # Read PatientID tag
        >>> patient_id = read_dicom_tag(Path("image.dcm"), (0x0010, 0x0020))
        >>> # Read StudyDate tag
        >>> study_date = read_dicom_tag(Path("image.dcm"), (0x0008, 0x0020))
        >>> # Read Modality tag
        >>> modality = read_dicom_tag(Path("image.dcm"), (0x0008, 0x0060))
    """
    try:
        # Read DICOM file, stopping before pixel data for efficiency
        dcm = pydicom.dcmread(str(file_path), stop_before_pixels=True)

        # Check if tag exists in the dataset
        if tag in dcm:
            value = dcm[tag].value
            # Convert value to string, handling various DICOM value types
            if value is None:
                return None
            return str(value)

        return None

    except FileNotFoundError as error:
        raise InvalidDicomError(f"DICOM file not found: {file_path}") from error

    except pydicom.errors.InvalidDicomError as error:
        raise InvalidDicomError(
            f"Invalid DICOM file: {file_path}. Error: {error}"
        ) from error

    except (OSError, ValueError) as error:
        raise InvalidDicomError(
            f"Failed to read DICOM file: {file_path}. Error: {error}"
        ) from error
