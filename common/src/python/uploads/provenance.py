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
    created_date: str
    modified_date: str

    @field_validator("created_date", "modified_date")
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
        # get the first version of the file to get the true creation
        # date. this is done because the created date of the current
        # file only corresponds to that version, which may be a reupload
        versions = proxy.get_file_versions(parent.file_id)
        if not len(versions) > 1:
            raise ValueError("parent file has no file version history")

        first_version = versions[0]
        if first_version.version != 1:
            raise ValueError("Version 1 of parent file not in expected position")

        return FileProvenance(
            file_id=parent.file_id,
            file_name=parent.name,
            flywheel_path=proxy.get_lookup_path(parent),
            created_date=first_version.created.isoformat(),
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
