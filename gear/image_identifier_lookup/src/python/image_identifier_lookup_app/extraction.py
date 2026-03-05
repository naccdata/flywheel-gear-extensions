"""Early data extraction utilities for the Image Identifier Lookup gear.

This module provides utilities for extracting required data from
Flywheel objects and pre-extracted DICOM metadata as early as possible
in the processing pipeline. All functions fail fast with clear error
messages when required data is missing.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from nacc_common.data_identification import DataIdentification

from image_identifier_lookup_app.dicom_utils import read_dicom_tags

log = logging.getLogger(__name__)


def extract_pipeline_adcid(project: ProjectAdaptor) -> int:
    """Extract pipeline ADCID from project metadata.

    Uses ProjectAdaptor.get_pipeline_adcid() which handles fallback
    from "pipeline_adcid" to "adcid" in project.info.

    Args:
        project: Project adaptor

    Returns:
        Pipeline ADCID as integer

    Raises:
        ProjectError: If ADCID missing from project metadata
    """
    return project.get_pipeline_adcid()


def extract_ptid(subject: SubjectAdaptor, dicom_metadata: dict) -> str:
    """Extract PTID from subject.label or DICOM PatientID.

    Priority:
    1. subject.label (if not empty)
    2. DICOM PatientID from pre-extracted metadata

    Args:
        subject: Subject adaptor
        dicom_metadata: Pre-extracted DICOM metadata dictionary

    Returns:
        PTID as string

    Raises:
        ValueError: If both sources are empty/missing
    """
    # Try subject.label first
    ptid = subject.label
    if ptid and ptid.strip():
        return ptid.strip()

    # Fallback to DICOM PatientID from metadata
    dicom_ptid = dicom_metadata.get("patient_id")
    if dicom_ptid and dicom_ptid.strip():
        return dicom_ptid.strip()

    raise ValueError(
        "PTID not found: subject.label is empty and DICOM PatientID is missing"
    )


def extract_existing_naccid(
    subject: SubjectAdaptor, naccid_field_name: str
) -> Optional[str]:
    """Extract existing NACCID from subject metadata.

    Args:
        subject: Subject adaptor
        naccid_field_name: Field name for NACCID in subject.info

    Returns:
        Existing NACCID if present, None otherwise
    """
    return subject.info.get(naccid_field_name)


def extract_visit_metadata(
    dicom_metadata: dict,
    ptid: str,
    adcid: int,
    naccid: Optional[str],
    default_modality: str,
) -> DataIdentification:
    """Extract visit metadata from pre-extracted DICOM metadata.

    Args:
        dicom_metadata: Pre-extracted DICOM metadata dictionary
        ptid: Pre-extracted PTID
        adcid: Pre-extracted pipeline ADCID
        naccid: Pre-extracted or looked-up NACCID
        default_modality: Default modality if DICOM tag missing

    Returns:
        DataIdentification instance with ImageIdentification

    Raises:
        ValueError: If required fields (StudyDate) are missing
    """
    # Extract date (required) - StudyDate is canonical per DICOM standard
    date = dicom_metadata.get("study_date")

    if not date:
        raise ValueError(
            "Visit date not found: StudyDate is missing (required DICOM field)"
        )

    # Extract modality (use default if missing)
    modality = dicom_metadata.get("modality")
    if not modality:
        log.warning(
            f"DICOM Modality tag (0008,0060) is missing for PTID={ptid}. "
            f"Using default modality: '{default_modality}'. "
            "This may indicate a data quality issue with the DICOM file."
        )
        modality = default_modality

    return DataIdentification.from_visit_metadata(
        ptid=ptid,
        date=format_dicom_date(date),  # Convert YYYYMMDD to YYYY-MM-DD
        modality=modality,
        adcid=adcid,
        naccid=naccid,
        visitnum=None,  # Images typically don't have visit numbers
    )


def extract_dicom_metadata(file_path: Path) -> dict[str, Any]:
    """Extract comprehensive DICOM metadata for storage.

    Extracts identifier and descriptive fields for tracking and reference.

    Args:
        file_path: Path to DICOM file

    Returns:
        Dictionary of DICOM metadata fields (None for missing optional fields)

    Raises:
        InvalidDicomError: If file is not valid DICOM
    """
    # Define all tags to read in a single operation
    tags = {
        # Identifier fields
        "patient_id": (0x0010, 0x0020),  # PatientID
        "study_instance_uid": (0x0020, 0x000D),  # StudyInstanceUID
        "series_instance_uid": (0x0020, 0x000E),  # SeriesInstanceUID
        "series_number": (0x0020, 0x0011),  # SeriesNumber
        # Date fields
        "study_date": (0x0008, 0x0020),  # StudyDate
        "series_date": (0x0008, 0x0021),  # SeriesDate
        # Descriptive fields
        "modality": (0x0008, 0x0060),  # Modality
        "magnetic_field_strength": (0x0018, 0x0087),  # MagneticFieldStrength
        "manufacturer": (0x0008, 0x0070),  # Manufacturer
        "manufacturer_model_name": (0x0008, 0x1090),  # ManufacturerModelName
        "series_description": (0x0008, 0x103E),  # SeriesDescription
        "images_in_acquisition": (0x0020, 0x1002),  # ImagesInAcquisition
    }

    # Read all tags in a single file read operation
    return read_dicom_tags(file_path, tags)


def format_dicom_date(dicom_date: str) -> str:
    """Convert DICOM date format (YYYYMMDD) to ISO format (YYYY-MM-DD).

    Args:
        dicom_date: Date in DICOM format (YYYYMMDD)

    Returns:
        Date in ISO format (YYYY-MM-DD)

    Raises:
        ValueError: If date format is invalid
    """
    if len(dicom_date) != 8:
        raise ValueError(f"Invalid DICOM date format: {dicom_date}")

    year = dicom_date[0:4]
    month = dicom_date[4:6]
    day = dicom_date[6:8]
    return f"{year}-{month}-{day}"
