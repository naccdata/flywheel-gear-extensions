import logging
from typing import Any, Dict, Optional

from deletions.models import DeleteRequest
from flywheel.models.file_entry import FileEntry
from nacc_common.data_identification import DataIdentification
from pydantic import ValidationError

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
                May contain the full form data payload or just metadata fields.

        Returns:
            DataIdentification instance or None if required fields are missing/invalid
        """
        if not forms_json:
            return None

        # Check for required fields before attempting to create DataIdentification
        module = forms_json.get("module")
        if not module:
            return None

        try:
            # Extract only the fields relevant to DataIdentification.
            # forms.json may contain the full form data (hundreds of fields),
            # so we must select only the keys that from_visit_metadata accepts.
            relevant_keys = {
                "adcid",
                "ptid",
                "naccid",
                "visitnum",
                "module",
                "packet",
                "modality",
            }
            mapped_data = {k: forms_json[k] for k in relevant_keys if k in forms_json}

            # Resolve the date field based on module.
            # NP module uses npformdate; all others use visitdate.
            # Fall back to visitdate if module-specific field is not present.
            date_field = "npformdate" if module.upper() == "NP" else "visitdate"
            date_value = forms_json.get(date_field) or forms_json.get("visitdate")
            if date_value:
                mapped_data["date"] = date_value

            return DataIdentification.from_visit_metadata(**mapped_data)
        except (ValidationError, ValueError, TypeError):
            return None
