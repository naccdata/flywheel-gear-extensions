"""Generic utilities involving files."""

import logging

from flywheel import FileEntry, FileSpec
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor

log = logging.getLogger(__name__)


def copy_file(
    file: FileEntry, destination: ProjectAdaptor, dry_run: bool = False
) -> None:
    """Copies the file to the destination project.

    Args:
      file: the file entry for the file
      destination: the destination project
      dry_run: whether or not this is a dry run
    """
    if dry_run:
        log.info(
            "DRY RUN: Would have copied %s to %s/%s",
            file.name,
            destination.group,
            destination.label,
        )
        return

    log.info(
        "copying file %s to %s/%s", file.name, destination.group, destination.label
    )

    raw_contents = file.read()
    file_spec = FileSpec(
        name=file.name,
        contents=raw_contents.decode("utf-8"),
        content_type=file.mimetype,
        size=len(raw_contents),
    )
    destination.upload_file(file_spec)
    destination.reload()
