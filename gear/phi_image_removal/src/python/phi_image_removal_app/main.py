"""Top-level orchestration for the PHI Image Removal gear.

Defines the run function that applies the per-file processor to the
input image file and reports the outcome.
"""

import logging

from flywheel import FileEntry
from flywheel.models.acquisition import Acquisition

from phi_image_removal_app.processor import PHIImageRemovalProcessor

log = logging.getLogger(__name__)


def run(
    *,
    file: FileEntry,
    acquisition: Acquisition,
    gear_name: str,
    gear_version: str | None,
    confirmed_tag: str,
    tombstone_tag: str,
    dry_run: bool = False,
) -> bool:
    """Runs the PHI Image Removal process for a single file.

    Args:
        file: the image file entry to evaluate
        acquisition: the acquisition that owns the file
        gear_name: name of this gear, recorded in the tombstone
        gear_version: version of this gear, recorded in the tombstone
        confirmed_tag: tag that marks a file as confirmed PHI
        tombstone_tag: tag added to the tombstone file
        dry_run: if True, log intended changes without applying them
    Returns:
        True if processing completed without error, False otherwise
    """
    processor = PHIImageRemovalProcessor(
        gear_name=gear_name,
        gear_version=gear_version,
        confirmed_tag=confirmed_tag,
        tombstone_tag=tombstone_tag,
        dry_run=dry_run,
    )

    try:
        outcome = processor.process(file=file, acquisition=acquisition)
    except Exception as error:
        log.error("Failed to remove PHI image %s: %s", file.name, error)
        return False

    if dry_run:
        log.info("Dry run complete; no changes were written")
    log.info("PHI Image Removal summary: file=%s outcome=%s", file.name, outcome.value)
    return True
