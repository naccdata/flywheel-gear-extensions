"""Early data extraction utilities for the Image Identifier Lookup gear.

This module provides the LookupContext model that accumulates all data
needed for the identifier lookup workflow. It is built incrementally:
first from Flywheel custom info, then optionally enriched with DICOM
metadata if needed.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, ProjectError
from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.model import clean_ptid
from nacc_common.data_identification import DataIdentification
from pydantic import BaseModel

from image_identifier_lookup_app.dicom_utils import read_dicom_tags

log = logging.getLogger(__name__)


class LookupContext(BaseModel):
    """Accumulated data for the identifier lookup workflow.

    Built in two phases:
    1. From Flywheel custom info (project and subject metadata)
    2. Optionally enriched with DICOM file data if needs_dicom() is True

    Fields are Optional because they may not be available from custom
    info alone.
    """

    pipeline_adcid: Optional[int] = None
    ptid: Optional[str] = None
    existing_naccid: Optional[str] = None
    study_date: Optional[str] = None
    modality: Optional[str] = None
    naccid_field_name: str = "naccid"
    dicom_metadata: Optional[dict[str, Any]] = None
    visit_metadata: Optional[DataIdentification] = None

    model_config = {"arbitrary_types_allowed": True}

    def needs_lookup(self) -> bool:
        """Whether a NACCID lookup is needed."""
        return self.existing_naccid is None

    def needs_dicom(self) -> bool:
        """Whether we need to open the input file.

        DICOM is needed when any of the fields that come from the DICOM
        file are missing: ptid (PatientID fallback), study_date, or
        modality. These may already be available from custom info if a
        previous run stored dicom_metadata in subject.info.
        """
        return self.ptid is None or self.study_date is None or self.modality is None

    def enrich_from_dicom(self, dicom_metadata: dict[str, Any]) -> None:
        """Enrich context with DICOM metadata.

        Fills in any gaps from custom info using DICOM data, and
        builds visit metadata for QC logging and event capture.

        Args:
            dicom_metadata: Extracted DICOM tag values

        Raises:
            ValueError: If required fields (PTID, StudyDate, Modality)
                cannot be resolved from any source
        """
        self.dicom_metadata = dicom_metadata

        # Fill PTID gap from DICOM PatientID
        if not self.ptid:
            dicom_ptid = dicom_metadata.get("patient_id")
            if dicom_ptid and dicom_ptid.strip():
                self.ptid = clean_ptid(dicom_ptid)
                log.info(f"Resolved PTID from DICOM PatientID: {self.ptid}")
            else:
                raise ValueError(
                    "PTID not found: subject.label is empty and "
                    "DICOM PatientID is missing"
                )

        # Fill study_date and modality from DICOM
        if not self.study_date:
            self.study_date = dicom_metadata.get("study_date")
        if not self.modality:
            self.modality = dicom_metadata.get("modality")

        self.build_visit_metadata()

    def build_visit_metadata(self) -> None:
        """Build visit metadata from resolved fields.

        Should be called after all fields are populated (either from
        custom info or DICOM enrichment). Sets visit_metadata if
        ptid, pipeline_adcid, study_date, and modality are all present.

        Raises:
            ValueError: If study_date or modality is missing
        """
        if not self.study_date:
            raise ValueError(
                "Visit date not found: StudyDate is missing (required DICOM field)"
            )
        if not self.modality:
            raise ValueError(
                "Modality not found: DICOM Modality tag (0008,0060) "
                "is missing (required DICOM field)"
            )
        if not self.ptid or self.pipeline_adcid is None:
            return

        self.visit_metadata = DataIdentification.from_visit_metadata(
            ptid=self.ptid,
            date=format_dicom_date(self.study_date),
            modality=self.modality,
            adcid=self.pipeline_adcid,
            naccid=self.existing_naccid,
            visitnum=None,
        )

    @classmethod
    def from_flywheel(
        cls,
        project: ProjectAdaptor,
        subject: SubjectAdaptor,
        naccid_field_name: str,
    ) -> "LookupContext":
        """Build context from Flywheel project and subject metadata.

        Collects what is available without raising on missing data.
        The caller should check needs_dicom() to decide whether DICOM
        extraction is needed.

        Args:
            project: Project adaptor
            subject: Subject adaptor
            naccid_field_name: Field name for NACCID in subject.info

        Returns:
            LookupContext with whatever fields are available
        """
        pipeline_adcid: Optional[int] = None
        try:
            pipeline_adcid = project.get_pipeline_adcid()
            log.info(f"Extracted pipeline ADCID: {pipeline_adcid}")
        except ProjectError:
            log.info("Pipeline ADCID not available from project metadata")

        ptid: Optional[str] = None
        label = subject.label
        if label and label.strip():
            ptid = clean_ptid(label)
            log.info(f"Extracted PTID from subject label: {ptid}")
        else:
            log.info("PTID not available from subject label")

        existing_naccid: Optional[str] = subject.info.get(naccid_field_name)
        if existing_naccid:
            log.info(f"Found existing NACCID in subject metadata: {existing_naccid}")
        else:
            log.info("No existing NACCID found in subject metadata")

        # Extract study_date and modality from previously stored dicom_metadata
        stored_dicom: dict = subject.info.get("dicom_metadata", {})
        study_date: Optional[str] = stored_dicom.get("study_date")
        modality: Optional[str] = stored_dicom.get("modality")
        if study_date and modality:
            log.info(
                f"Found study_date={study_date} and modality={modality} "
                "from stored dicom_metadata"
            )

        ctx = cls(
            pipeline_adcid=pipeline_adcid,
            ptid=ptid,
            existing_naccid=existing_naccid,
            study_date=study_date,
            modality=modality,
            naccid_field_name=naccid_field_name,
            dicom_metadata=stored_dicom or None,
        )

        # If all fields are present, build visit metadata now
        if not ctx.needs_dicom() and ctx.pipeline_adcid is not None:
            ctx.build_visit_metadata()

        return ctx


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
    tags = {
        "patient_id": (0x0010, 0x0020),
        "study_instance_uid": (0x0020, 0x000D),
        "series_instance_uid": (0x0020, 0x000E),
        "series_number": (0x0020, 0x0011),
        "study_date": (0x0008, 0x0020),
        "series_date": (0x0008, 0x0021),
        "modality": (0x0008, 0x0060),
        "magnetic_field_strength": (0x0018, 0x0087),
        "manufacturer": (0x0008, 0x0070),
        "manufacturer_model_name": (0x0008, 0x1090),
        "series_description": (0x0008, 0x103E),
        "images_in_acquisition": (0x0020, 0x1002),
    }

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
