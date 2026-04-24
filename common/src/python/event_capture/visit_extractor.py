import logging
from typing import Any, Dict, Optional

from flywheel.models.file_entry import FileEntry
from nacc_common.data_identification import (
    DataIdentification,
)
from pydantic import ValidationError
from submissions.models import DeleteRequest

log = logging.getLogger(__name__)


class DataIdentificationExtractor:
    """Utility for extracting DataIdentification from QC status or JSON
    files."""

    @staticmethod
    def from_qc_status_custom_info(
        custom_info: Dict[str, Any],
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from QC status custom info.

        Args:
            custom_info: Custom info from QC status log file

        Returns:
            DataIdentification instance or None if not found/invalid
        """
        if not custom_info:
            return None

        visit_data = custom_info.get("visit")
        if not visit_data:
            return None

        try:
            return DataIdentification.from_visit_metadata(**visit_data)
        except (ValidationError, ValueError, TypeError):
            return None

    @staticmethod
    def from_json_file_metadata(json_file: FileEntry) -> Optional[DataIdentification]:
        """Extract DataIdentification from JSON file forms metadata.

        The forms.json metadata uses normalized field names (visitdate, not
        module-specific date fields) since it's been processed during upload.

        Args:
            json_file: JSON file with forms metadata

        Returns:
            DataIdentification instance or None if not found/invalid
        """
        if not json_file or not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        return DataIdentificationExtractor.from_forms_json(forms_json)

    @staticmethod
    def from_deletion_request_file(
        request_file: FileEntry,
        adcid: int,
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from a deletion request file.

        Reads and parses the deletion request JSON file content.

        Args:
            request_file: The deletion request FileEntry
            adcid: The ADC ID for the project

        Returns:
            DataIdentification instance or None if parsing fails
        """
        try:
            content = request_file.read().decode("utf-8")
            delete_request = DeleteRequest.model_validate_json(content)
            return DataIdentification.from_visit_metadata(
                adcid=adcid,
                ptid=delete_request.ptid,
                date=delete_request.visitdate,
                module=delete_request.module,
                visitnum=delete_request.visitnum,
            )
        except (ValidationError, ValueError, TypeError) as error:
            log.error(
                "Failed to extract data identification from %s: %s",
                request_file.name,
                error,
            )
            return None

    @staticmethod
    def from_forms_json(forms_json: dict[str, Any]) -> Optional[DataIdentification]:
        """Extract DataIdentification from forms.json dict.

        Args:
            forms_json: Dictionary with forms metadata (ptid, visitdate, module, etc.)

        Returns:
            DataIdentification instance or None if required fields are missing/invalid
        """
        if not forms_json:
            return None

        # Check for required fields before attempting to create DataIdentification
        if not forms_json.get("module"):
            return None

        try:
            # Map visitdate to date for from_visit_metadata
            # forms.json uses normalized field names after upload processing
            mapped_data = {**forms_json}
            if "visitdate" in mapped_data:
                mapped_data["date"] = mapped_data.pop("visitdate")
            return DataIdentification.from_visit_metadata(**mapped_data)
        except (ValidationError, ValueError, TypeError):
            return None
