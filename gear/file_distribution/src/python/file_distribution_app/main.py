"""Defines File Distribution."""

import logging
from typing import List, Optional

from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from jobs.job_poll import JobPoll
from outputs.error_writer import ListErrorWriter
from projects.project_mapper import build_project_map
from utils.files import copy_file

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    error_writer: ListErrorWriter,
    file: FileEntry,
    target_project: str,
    centers=List[str],
    batch_size=int,
    downstream_gears: Optional[List[str]] = None,
):
    """Runs the File Distribution process.

    Args:
        proxy: the proxy for the Flywheel instance
        error_writer: The ListErrorWriter to write errors to
        file: File to copy to projects
        target_project: The FW target project name to write results to for
                        each ADCID in centers
        centers: Set of ADCIDs to copy file for
        batch_size: Number of centers to put in each batch for scheduling
        downstream_gears: Gears to wait on before processing the
            next batch when scheduling
    """
    project_map = build_project_map(
        proxy=proxy, destination_label=target_project, center_filter=list(centers)
    )

    if not project_map:
        raise GearExecutionError(f"No {target_project} projects found")

    batched_centers = [
        centers[i : i + batch_size] for i in range(0, len(centers), batch_size)
    ]

    # write results to each center's project
    for i, batch in enumerate(batched_centers, start=1):
        log.info(f"Running batch {i} of {len(batched_centers)}")
        project_ids_list = []

        for adcid in batch:
            project = project_map[f"adcid-{adcid}"]

            if proxy.dry_run:
                log.info(
                    "DRY RUN: Would have copied %s to %s/%s",
                    file.name,
                    project.group,
                    project.label,
                )
                continue

            copy_file(file, project)
            project_ids_list.append(project.id)

        if project_ids_list and downstream_gears:
            JobPoll.wait_for_batched_group(
                proxy=proxy,
                project_ids_list=project_ids_list,
                downstream_gears=downstream_gears,
            )
