"""Generic utilities involving files."""

import logging

from flywheel import FileEntry, FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor

log = logging.getLogger(__name__)


def check_duplicate_project_file(
    project: ProjectAdaptor,
    contents: str,
    filename: str,
) -> bool:
    """Check if the uploaded file would be an exact duplicate of an existing
    project file.

    Args:
        project: The target project to upload the file to
        contents: String contents of the file to upload
        filename: File name of the file to upload
    Returns:
        Whether or not the file is a duplicate of an existing file
            on the target project
    """
    project_name = f"{project.group}/{project.label}"

    try:
        existing_data = project.read_file(filename)
    except ApiException as e:
        log.info(f"Could not read {filename} on {project_name}: {e}")
        return False

    is_duplicate = contents.encode("utf-8") == existing_data
    log.info(
        f"Contents for {filename} is {'' if is_duplicate else 'NOT '}"
        + f"a duplicate on {project_name}"
    )

    return is_duplicate


def copy_file(
    file: FileEntry,
    destination: ProjectAdaptor,
    dry_run: bool = False,
    replace_duplicates: bool = True,
) -> None:
    """Copies the file to the destination project.

    Args:
      file: the file entry for the file
      destination: the destination project
      dry_run: whether or not this is a dry run
      replace_duplicates: Replace a file even if it's an
        exact duplicate of an existing file
    """
    if dry_run:
        log.info(
            "DRY RUN: Would have copied %s to %s/%s",
            file.name,
            destination.group,
            destination.label,
        )
        return

    raw_contents = file.read()
    contents = raw_contents.decode("utf-8")

    if not replace_duplicates and check_duplicate_project_file(
        destination,
        contents,
        file.name,
    ):
        log.info("Duplicate data, skipping upload of %s", file.name)
        return

    log.info(
        "copying file %s to %s/%s", file.name, destination.group, destination.label
    )

    file_spec = FileSpec(
        name=file.name,
        contents=contents,
        content_type=file.mimetype,
        size=len(raw_contents),
    )
    destination.upload_file(file_spec)
    destination.reload()
