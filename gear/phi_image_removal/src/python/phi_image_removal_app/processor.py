"""Per-file processing for the PHI Image Removal gear.

Defines the Outcome result type and PHIImageRemovalProcessor, which
replaces a PHI-confirmed image file with a JSON tombstone: it captures
the file's details, uploads the tombstone, tags it, and deletes the
original.
"""

import logging
from datetime import datetime, timezone
from enum import Enum

from flywheel import FileEntry
from flywheel.file_spec import FileSpec
from flywheel.models.acquisition import Acquisition

from phi_image_removal_app.tombstone import build_tombstone, tombstone_filename

log = logging.getLogger(__name__)


class PHIImageRemovalError(Exception):
    """Raised when the tombstone cannot be created safely."""


class Outcome(str, Enum):
    """Result of processing a single image file."""

    REMOVED = "removed"
    SKIPPED = "skipped"


class PHIImageRemovalProcessor:
    """Replaces a PHI-confirmed image file with a JSON tombstone."""

    def __init__(
        self,
        *,
        gear_name: str,
        gear_version: str | None,
        confirmed_tag: str,
        tombstone_tag: str,
        dry_run: bool,
    ):
        """Initialize the processor with configuration.

        Args:
            gear_name: name of this gear, recorded in the tombstone
            gear_version: version of this gear, recorded in the tombstone
            confirmed_tag: tag that marks a file as confirmed PHI
            tombstone_tag: tag added to the tombstone file
            dry_run: whether to log intended changes without applying them
        """
        self.__gear_name = gear_name
        self.__gear_version = gear_version
        self.__confirmed_tag = confirmed_tag
        self.__tombstone_tag = tombstone_tag
        self.__dry_run = dry_run

    def process(self, *, file: FileEntry, acquisition: Acquisition) -> Outcome:
        """Tombstones the file if it is confirmed PHI.

        Ordered so the original is never deleted without a tagged tombstone
        already in place: upload the tombstone, tag it, then delete the image.

        Args:
            file: the image file entry to evaluate
            acquisition: the acquisition that owns the file
        Returns:
            the Outcome describing what was done
        Raises:
            PHIImageRemovalError: if the tombstone is missing after upload
        """
        if self.__confirmed_tag not in (file.tags or []):
            log.info(
                "File %s does not have tag '%s'; nothing to do",
                file.name,
                self.__confirmed_tag,
            )
            return Outcome.SKIPPED

        tombstone_name = tombstone_filename(file.name)
        if acquisition.get_file(tombstone_name) is not None:
            log.warning(
                "Tombstone %s already exists in acquisition %s; skipping",
                tombstone_name,
                acquisition.label,
            )
            return Outcome.SKIPPED

        record = build_tombstone(
            file,
            gear_name=self.__gear_name,
            gear_version=self.__gear_version,
            removed_at=datetime.now(timezone.utc).isoformat(),
            reason=self.__confirmed_tag,
        )
        contents = record.model_dump_json(indent=2)

        if self.__dry_run:
            log.info(
                "Dry run: would upload tombstone %s, tag it '%s', and delete %s",
                tombstone_name,
                self.__tombstone_tag,
                file.name,
            )
            return Outcome.REMOVED

        # 1. Upload the tombstone first, so the image is never deleted without
        #    a record left in its place.
        file_spec = FileSpec(
            name=tombstone_name, contents=contents, content_type="application/json"
        )
        acquisition.upload_file(file_spec)
        log.info(
            "Uploaded tombstone %s to acquisition %s", tombstone_name, acquisition.label
        )

        # 2. Tag the tombstone.
        acquisition = acquisition.reload()
        tombstone = acquisition.get_file(tombstone_name)
        if tombstone is None:
            raise PHIImageRemovalError(
                f"Tombstone {tombstone_name} not found after upload; "
                f"leaving original file {file.name} in place"
            )
        tombstone.add_tag(self.__tombstone_tag)
        log.info("Tagged tombstone %s with '%s'", tombstone_name, self.__tombstone_tag)

        # 3. Delete the original PHI image last.
        # delete_file is a runtime container method missing from the SDK stubs.
        acquisition.delete_file(file.name)  # type: ignore[attr-defined]
        log.info(
            "Deleted PHI image %s from acquisition %s", file.name, acquisition.label
        )

        return Outcome.REMOVED
