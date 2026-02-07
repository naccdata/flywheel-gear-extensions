import logging
from typing import Any, Dict, Optional

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import (
    VisitMetadata,
)
from pydantic import ValidationError

log = logging.getLogger(__name__)


class VisitMetadataExtractor:
    """Utility for extracting VisitMetadata from QC status or JSON files."""

    @staticmethod
    def from_qc_status_custom_info(
        custom_info: Dict[str, Any],
    ) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from QC status custom info.

        Args:
            custom_info: Custom info from QC status log file

        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        if not custom_info:
            return None

        visit_data = custom_info.get("visit")
        if not visit_data:
            return None

        try:
            return VisitMetadata.model_validate(visit_data)
        except ValidationError:
            return None

    @staticmethod
    def from_json_file_metadata(json_file: FileEntry) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from JSON file forms metadata.

        Args:
            json_file: JSON file with forms metadata

        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        if not json_file or not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        try:
            # Create mapping for field name differences
            mapped_data = {**forms_json, "date": forms_json.get("visitdate")}
            return VisitMetadata.model_validate(mapped_data)
        except ValidationError:
            return None

    @staticmethod
    def is_valid_for_event(visit_metadata: VisitMetadata) -> bool:
        """Check if VisitMetadata has required fields for VisitEvent
        creation."""
        if not visit_metadata:
            return False

        return bool(
            visit_metadata.ptid and visit_metadata.date and visit_metadata.module
        )
