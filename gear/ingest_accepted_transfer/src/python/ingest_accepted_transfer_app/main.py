"""Defines Ingest Accepted Transfer."""

import logging
from datetime import date, timedelta
from functools import total_ordering
from heapq import heappop, heappush
from typing import List, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_trigger import trigger_gear
from jobs.job_poll import JobPoll

log = logging.getLogger(__name__)


@total_ordering
class Element:

    def __init__(self, source, target) -> None:
        self.source = source
        self.target = target

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Element):
            return False
        return self.source.id == value.source.id

    def __lt__(self, value: object) -> bool:
        if not isinstance(value, Element):
            return False
        return (self.source.stats.number_of.acquisition_files
                < value.source.stats.number_of.acquisition_files)

    @property
    def count(self) -> int:
        return self.source.stats.number_of.acquisition_files


def trigger_copy_for_center(proxy: FlywheelProxy, gear_name: str,
                            center: Element) -> Optional[str]:
    """Trigger the ingest to accepted copy for specified center.

    Args:
        proxy: Flywheel proxy
        gear_name: copy gear name
        center: center information

    Returns:
        Optional[str]: gear job id or None
    """

    # TODO: get copy gear configs from configs file
    job_id = trigger_gear(proxy=proxy,
                          gear_name=gear_name,
                          config={
                              "debug": False,
                              "destination_project": center.target.id,
                              "duplicate_check_projects": center.target.id,
                              "modified_match_fields": "file.hash",
                              "required_match_fields": "file.name, file.hash",
                              "tag_to_copy": "file-validator-PASS"
                          },
                          inputs={},
                          destination=center.source)

    return job_id


def get_batch(centers: List[Element], batch_size: int) -> List[Element]:
    """Get a batch of centers depending on number of acquisition files.

    Args:
        centers: list of centers in the ascending order of acquisition files
        batch_size: number of acquisition files to queue for one batch

    Returns:
        List[Element]: current batch
    """
    batch = []
    total_count = 0
    while len(centers) > 0 and total_count < batch_size:
        element = heappop(centers)
        batch.append(element)
        total_count += element.count
    return batch


def check_batch_run_status(proxy: FlywheelProxy, jobs_list: List[str],
                           failed_list: List[str]):
    """Checks the job completion status of the jobs in current batch Keeps
    polling job status until all jobs in the current batch complete.

    Args:
        proxy: Flywheel proxy
        jobs_list: list of job ids in current batch
        failed_list: list of failed jobs
    """
    if not jobs_list:
        return

    for job_id in jobs_list:
        if not JobPoll.is_job_complete(proxy, job_id):
            failed_list.append(job_id)


def schedule_batch_copy(proxy: FlywheelProxy, centers: List[Element],
                        batch_size: int, gear_name: str):
    """Schedule the centers in batches depending on number of acquisitions
    files in the ingest project and batch size.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        batch_size: number of acquisition files to queue for one batch
        gear_name: copy gear name
    """

    failed_list: List[str] = []
    jobs_list: List[str] = []
    batch = get_batch(centers=centers, batch_size=batch_size)
    while len(batch) > 0:
        log.info('Batch size: %s', len(batch))
        for center in batch:
            group_id = center.source.group
            project_lbl = center.source.label
            job_id = trigger_copy_for_center(proxy=proxy,
                                             center=center,
                                             gear_name=gear_name)
            if not job_id:
                log.error('Failed to trigger gear %s for  %s/%s', gear_name,
                          group_id, project_lbl)
                continue

            log.info('Gear %s queued for %s/%s - Job ID %s', gear_name,
                     group_id, project_lbl, job_id)
            jobs_list.append(job_id)

        check_batch_run_status(proxy,
                               jobs_list=jobs_list,
                               failed_list=failed_list)

        # clear the jobs list
        # all the jobs in current batch are finished when it gets to this point
        jobs_list.clear()

        batch = get_batch(centers=centers, batch_size=batch_size)

    if len(failed_list) > 0:
        log.error('Failed %s ingest to accepted copy jobs: %s',
                  len(failed_list), str(failed_list))


def get_centers_to_copy(proxy: FlywheelProxy, center_ids: List[str],
                        time_interval: int, copy_gear: str) -> List[str]:
    """Get the list of centers to copy data matching with the given time
    interval.

    Args:
        proxy: Flywheel proxy
        center_ids: list of centers to copy data
        time_interval: time interval in days between the copy gear runs
        copy_gear: copy gear name

    Returns:
        List[str]: list of center ids
    """

    today = date.today()
    centers_to_copy = []

    for center in center_ids:
        search_str = f'parents.group={center},state=complete,gear_info.name={copy_gear}'
        job = proxy.find_job(search_str, sort='created:desc')
        if job and (today - job.transitions['complete'].date()  # type: ignore
                    ) <= timedelta(days=time_interval):
            continue

        centers_to_copy.append(center)

    return centers_to_copy


def run(*, proxy: FlywheelProxy, centers: List[str], ingest_project_lbl: str,
        accepted_project_lbl: str, time_interval: int, batch_size: int,
        dry_run: bool):
    """Runs the ingest to accepted transfer process.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        ingest_project: ingest project label
        accepted_project: accepted project label
        time_interval: time interval in days between the runs (input -1 to ignore)
        batch_size: number of acquisition files to queue for one batch
        dry_run: whether to do a dry run
    """

    copy_gear = 'duplicate-aware-project-copy'

    centers_to_copy = get_centers_to_copy(
        center_ids=centers,
        proxy=proxy,
        time_interval=time_interval,
        copy_gear=copy_gear) if time_interval > 0 else centers

    minheap: List[Element] = []
    for center_id in centers_to_copy:
        try:
            ingest_project = proxy.lookup(f"{center_id}/{ingest_project_lbl}")
            if ingest_project.stats.number_of.acquisition_files > 0:
                accepted_project = proxy.lookup(
                    f"{center_id}/{accepted_project_lbl}")
                heappush(
                    minheap,
                    Element(source=ingest_project, target=accepted_project))
                log.info(center_id)
        except ApiException as error:
            log.error('Error occurred for %s: %s', center_id, str(error))
            continue

    if not len(minheap) > 0:
        log.info('No ingest projects to copy')
        return

    log.info('Number of ingest projects to copy: %s', len(minheap))

    if dry_run:
        log.info('dry run, not copying data')
        return

    schedule_batch_copy(proxy=proxy,
                        centers=minheap,
                        batch_size=batch_size,
                        gear_name=copy_gear)
