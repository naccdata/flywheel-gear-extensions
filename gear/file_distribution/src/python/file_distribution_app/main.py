"""Defines File Distribution."""

import logging
from typing import List, Optional

from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from jobs.job_poll import JobPoll
from outputs.error_writer import ListErrorWriter
from projects.project_mapper import build_project_map
from utils.files import copy_file

log = logging.getLogger(__name__)


def copy_file_to_project(
    proxy: FlywheelProxy, file: FileEntry, project: ProjectAdaptor
):
    if proxy.dry_run:
        log.info(
            "DRY RUN: Would have copied %s to %s/%s",
            file.name,
            project.group,
            project.label,
        )
        return

    copy_file(file, project)


def run(
    *,
    proxy: FlywheelProxy,
    error_writer: ListErrorWriter,
    file: FileEntry,
    centers=List[str],
    batch_size=int,
    target_project: Optional[str] = None,
    staging_project_id: Optional[str] = None,
    downstream_gears: Optional[List[str]] = None,
):
    """Runs the File Distribution process.

    Args:
        proxy: the proxy for the Flywheel instance
        error_writer: The ListErrorWriter to write errors to
        file: File to copy to projects
        centers: Set of ADCIDs to copy file for
        batch_size: Number of centers to put in each batch for scheduling
        target_project: The FW target project name to write results to for
                        each ADCID in centers
        staging_project_id: Target staging project to write file to instead
        downstream_gears: Gears to wait on before processing the
            next batch when scheduling
    """
    # if staging_project_id, really just have to do it once since
    # we're not splitting files
    if staging_project_id:
        log.info("staging_project_id provided, just copying file over")
        fw_project = proxy.get_project_by_id(staging_project_id)
        if not fw_project:
            raise GearExecutionError(
                f"Cannot find staging project with ID {staging_project_id}, "
                + "possibly a permissions issue?"
            )

        staging_project = ProjectAdaptor(project=fw_project, proxy=proxy)
        copy_file_to_project(proxy, file, staging_project)
        return

    assert target_project, "target_project required if no staging_project_id provided"
    project_map = build_project_map(
        proxy=proxy, destination_label=target_project, center_filter=list(centers)
    )

    if not project_map:
        raise GearExecutionError(f"No {target_project} projects found")

    found_centers = list(project_map.keys())
    batched_centers = [
        found_centers[i : i + batch_size]
        for i in range(0, len(found_centers), batch_size)
    ]
    log.info(f"target_project provided, copying file to {len(found_centers)} centers")

    # write results to each center's project
    for i, batch in enumerate(batched_centers, start=1):
        log.info(f"Running batch {i} of {len(batched_centers)}")
        project_ids_list = []

        for adcid in batch:
            project = project_map[adcid]
            copy_file_to_project(proxy, file, project)
            project_ids_list.append(project.id)

        if project_ids_list and downstream_gears:
            JobPoll.wait_for_batched_group(
                proxy=proxy,
                project_ids_list=project_ids_list,
                downstream_gears=downstream_gears,
            )
