import logging
from datetime import datetime
from typing import Optional

from flywheel.models.file_entry import FileEntry
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from pydantic import BaseModel, ValidationError, field_validator
from utils.decorators import api_retry

log = logging.getLogger(__name__)


class FileProvenance(BaseModel):
    file_id: str
    file_name: str
    flywheel_path: str
    modified_date: str

    @field_validator("modified_date")
    def validate_iso_format(cls, v: str) -> str:
        """Ensure the modified date is in ISO format."""
        try:
            value = datetime.fromisoformat(v)
        except ValueError as e:
            raise ValueError(
                f"Provided modified_date {v} is not in ISO format: {e}"
            ) from e

        return value.isoformat()

    @classmethod
    @api_retry
    def create_from_parent(
        cls, proxy: FlywheelProxy, parent: FileEntry
    ) -> "FileProvenance":
        """Create file provenance from parent FileEntry."""
        return FileProvenance(
            file_id=parent.file_id,
            file_name=parent.name,
            flywheel_path=proxy.get_lookup_path(parent),
            modified_date=parent.modified.isoformat(),
        )

    @classmethod
    @api_retry
    def create_from_child(cls, child: FileEntry) -> Optional["FileProvenance"]:
        """Get provenance from child FileEntry, if it exists."""
        child = child.reload()
        provenance = child.info.get("provenance", {})

        if provenance and isinstance(provenance, dict):
            try:
                return FileProvenance(**provenance)
            except ValidationError:
                pass

        log.info("No provenance information for %s", child.name)
        return None

    @api_retry
    def set_provenance(self, target: FileEntry) -> bool:
        """Set self provenance on target FileEntry."""
        try:
            target.update_info({"provenance": self.model_dump()})
        except ApiException as error:
            log.error("Error in setting file %s metadata - %s", target.name, error)
            return False

        return True
