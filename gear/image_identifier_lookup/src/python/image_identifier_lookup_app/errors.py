"""Error handling utilities for Image Identifier Lookup gear.

This module provides centralized error handling for the Image Identifier
Lookup gear, creating FileError objects with appropriate context for
different error scenarios.
"""

from typing import Optional

from nacc_common.data_identification import DataIdentification
from nacc_common.error_models import FileError


class ErrorHandler:
    """Centralized error handling for Image Identifier Lookup gear.

    This class provides methods to create FileError objects for various
    error scenarios that can occur during image identifier lookup
    processing. All methods return FileError objects with appropriate
    context and error codes.
    """

    @staticmethod
    def create_ptid_extraction_error(
        error: Exception,
        visit_keys: Optional[DataIdentification] = None,
    ) -> FileError:
        """Create a FileError for PTID extraction failures.

        This error occurs when the PTID cannot be extracted from either
        subject.label or the DICOM PatientID tag.

        Args:
            error: The exception that occurred during PTID extraction
            visit_keys: Optional DataIdentification for context

        Returns:
            FileError object for PTID extraction error
        """
        return FileError(
            error_type="error",
            error_code="ptid-extraction-error",
            message=(
                f"Failed to extract PTID: {error!s}. "
                "PTID must be present in subject.label or DICOM PatientID tag."
            ),
            ptid=visit_keys.ptid if visit_keys else None,
            visitnum=visit_keys.visitnum if visit_keys else None,
            date=visit_keys.date if visit_keys else None,
            naccid=visit_keys.naccid if visit_keys else None,
        )

    @staticmethod
    def create_lookup_error(
        ptid: str,
        adcid: int,
        error: Exception,
        visit_keys: Optional[DataIdentification] = None,
    ) -> FileError:
        """Create a FileError for identifier lookup failures.

        This error occurs when the NACCID lookup fails, either because
        no matching record was found or the lookup service is unavailable.

        Args:
            ptid: The participant identifier used for lookup
            adcid: The ADCID used for lookup
            error: The exception that occurred during lookup
            visit_keys: Optional DataIdentification for context

        Returns:
            FileError object for lookup error
        """
        return FileError(
            error_type="error",
            error_code="identifier-lookup-error",
            message=(
                f"Failed to lookup NACCID for PTID={ptid}, ADCID={adcid}: {error!s}"
            ),
            value=ptid,
            ptid=visit_keys.ptid if visit_keys else ptid,
            visitnum=visit_keys.visitnum if visit_keys else None,
            date=visit_keys.date if visit_keys else None,
            naccid=visit_keys.naccid if visit_keys else None,
        )

    @staticmethod
    def create_metadata_conflict_error(
        ptid: str,
        existing: str,
        new: str,
        visit_keys: Optional[DataIdentification] = None,
    ) -> FileError:
        """Create a FileError for NACCID metadata conflicts.

        This error occurs when the existing NACCID in subject metadata
        differs from the NACCID returned by the lookup service.

        Args:
            ptid: The participant identifier
            existing: The existing NACCID in subject metadata
            new: The new NACCID from lookup
            visit_keys: Optional DataIdentification for context

        Returns:
            FileError object for metadata conflict error
        """
        return FileError(
            error_type="error",
            error_code="naccid-conflict-error",
            message=(
                f"NACCID conflict for PTID={ptid}: "
                f"existing NACCID={existing}, lookup result={new}. "
                "The NACCID in subject metadata does not match the lookup result."
            ),
            value=existing,
            expected=new,
            ptid=visit_keys.ptid if visit_keys else ptid,
            visitnum=visit_keys.visitnum if visit_keys else None,
            date=visit_keys.date if visit_keys else None,
            naccid=visit_keys.naccid if visit_keys else existing,
        )

    @staticmethod
    def create_dicom_parsing_error(
        error: Exception,
        file_path: Optional[str] = None,
        visit_keys: Optional[DataIdentification] = None,
    ) -> FileError:
        """Create a FileError for DICOM parsing failures.

        This error occurs when the input file cannot be parsed as a valid
        DICOM file or when required DICOM tags are missing.

        Args:
            error: The exception that occurred during DICOM parsing
            file_path: Optional path to the DICOM file
            visit_keys: Optional DataIdentification for context

        Returns:
            FileError object for DICOM parsing error
        """
        message = f"Failed to parse DICOM file: {error!s}"
        if file_path:
            message = f"Failed to parse DICOM file '{file_path}': {error!s}"

        return FileError(
            error_type="error",
            error_code="dicom-parsing-error",
            message=message,
            ptid=visit_keys.ptid if visit_keys else None,
            visitnum=visit_keys.visitnum if visit_keys else None,
            date=visit_keys.date if visit_keys else None,
            naccid=visit_keys.naccid if visit_keys else None,
        )
