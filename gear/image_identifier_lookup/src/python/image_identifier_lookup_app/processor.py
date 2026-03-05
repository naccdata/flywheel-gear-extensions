"""Core business logic for image identifier lookup.

This module implements the ImageIdentifierLookupProcessor class which
handles the core business logic for looking up NACCIDs and updating
subject metadata. The processor receives pre-extracted data as
parameters and does not access Flywheel objects directly, making it
easier to test and reason about.
"""

import logging
from typing import Any, Optional

from flywheel_adaptor.subject_adaptor import SubjectAdaptor
from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)

log = logging.getLogger(__name__)


class ImageIdentifierLookupProcessor:
    """Processes identifier lookup using pre-extracted data.

    This processor focuses purely on business logic and does not access
    Flywheel objects directly. All required data is provided as
    parameters.
    """

    def __init__(
        self,
        *,
        identifiers_repository: IdentifierRepository,
        subject: SubjectAdaptor,
        naccid_field_name: str,
    ):
        """Initialize processor with minimal dependencies.

        Args:
            identifiers_repository: Repository for NACCID lookups
            subject: Subject adaptor for metadata updates
            naccid_field_name: Field name for NACCID in subject.info
        """
        self.__identifiers_repository = identifiers_repository
        self.__subject = subject
        self.__naccid_field_name = naccid_field_name

    def lookup_and_update(
        self,
        ptid: str,
        adcid: int,
        dicom_metadata: dict[str, Any],
    ) -> str:
        """Look up NACCID and update subject metadata.

        Args:
            ptid: Pre-extracted participant identifier
            adcid: Pre-extracted pipeline ADCID
            dicom_metadata: Comprehensive DICOM metadata to store

        Returns:
            The looked-up NACCID

        Raises:
            IdentifierRepositoryError: If no matching record found or lookup
                service unavailable
            ApiException: If metadata update fails
        """
        # Look up NACCID using PTID and ADCID
        naccid = self._lookup_naccid(ptid, adcid)

        # Update subject metadata with NACCID and DICOM metadata
        self._update_subject_metadata(naccid, dicom_metadata)

        return naccid

    def _lookup_naccid(self, ptid: str, adcid: int) -> str:
        """Look up NACCID using PTID and ADCID.

        Uses IdentifiersLambdaRepository.get() method.

        Args:
            ptid: Participant identifier
            adcid: Pipeline ADCID

        Returns:
            NACCID as string

        Raises:
            IdentifierRepositoryError: If no matching record found or lookup
                service unavailable
        """
        log.info(f"Looking up NACCID for PTID={ptid}, ADCID={adcid}")

        identifier = self.__identifiers_repository.get(adcid=adcid, ptid=ptid)

        if not identifier:
            raise IdentifierRepositoryError(
                f"No matching identifier record found for PTID={ptid}, ADCID={adcid}"
            )

        log.info(f"NACCID lookup successful: {identifier.naccid}")
        return identifier.naccid

    def _update_subject_metadata(
        self, naccid: str, dicom_metadata: dict[str, Any]
    ) -> None:
        """Store NACCID and DICOM metadata in subject.info.

        Uses SubjectAdaptor.update() to update subject.info with both the
        NACCID and comprehensive DICOM metadata.

        Args:
            naccid: NACCID to store
            dicom_metadata: Comprehensive DICOM metadata to store

        Raises:
            ApiException: If metadata update fails
        """
        log.info(f"Updating subject metadata with NACCID: {naccid}")

        # Prepare update dictionary with NACCID and DICOM metadata
        updates = {
            self.__naccid_field_name: naccid,
            "dicom_metadata": dicom_metadata,
        }

        self.__subject.update(info=updates)
        log.info("Subject metadata updated successfully")
