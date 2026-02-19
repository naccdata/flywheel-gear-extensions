import logging
from typing import Any, Dict, Optional

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import (
    DataIdentification,
)
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
        except (ValidationError, TypeError):
            return None

    @staticmethod
    def from_json_file_metadata(json_file: FileEntry) -> Optional[DataIdentification]:
        """Extract DataIdentification from JSON file forms metadata.

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

        try:
            # Map visitdate to date for from_visit_metadata
            mapped_data = {**forms_json}
            if "visitdate" in mapped_data:
                mapped_data["date"] = mapped_data.pop("visitdate")
            return DataIdentification.from_visit_metadata(**mapped_data)
        except (ValidationError, TypeError):
            return None
