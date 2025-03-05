"""Defines Ingest Accepted Transfer."""

import logging
from datetime import date, timedelta
from functools import total_ordering
from heapq import heappop, heappush
from typing import List, Optional

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_trigger import BatchRunInfo, trigger_gear
from jobs.job_poll import JobPoll

log = logging.getLogger(__name__)


@total_ordering
class Element:

    def __init__(self, source, target, count_files=True) -> None:
        self.source = source
        self.target = target
        self.count_files = count_files

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
        if self.count_files:
            return self.source.stats.number_of.acquisition_files

        return 1


def trigger_gear_for_center(proxy: FlywheelProxy, batch_configs: BatchRunInfo,
                            center: Element) -> Optional[str]:
    """Trigger the gear for specified center.

    Args:
        proxy: Flywheel proxy
        batch_configs: batch run configs
        center: center information

    Returns:
        Optional[str]: gear job id or None
    """

    gear_configs = batch_configs.get_gear_configs(source=center.source.id,
                                                  target=center.target.id)

    job_id = trigger_gear(proxy=proxy,
                          gear_name=batch_configs.gear_name,
                          config=gear_configs,
                          inputs={},
                          destination=center.source)

    return job_id


def get_batch(centers: List[Element], batch_size: int) -> List[Element]:
    """Get a batch of centers depending on the batch size.

    Args:
        centers: list of centers in the ascending order of acquisition files
        batch_size: number of projects or files to queue for one batch

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
                        batch_configs: BatchRunInfo):
    """Schedule the centers in batches depending on the batch mode and batch
    size.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        batch_configs: batch run configurations
    """

    failed_list: List[str] = []
    jobs_list: List[str] = []
    batch = get_batch(centers=centers, batch_size=batch_configs.batch_size)
    while len(batch) > 0:
        log.info('Scheduling %s on %s centers', batch_configs.gear_name,
                 len(batch))
        for center in batch:
            group_id = center.source.group
            project_lbl = center.source.label
            job_id = trigger_gear_for_center(proxy=proxy,
                                             center=center,
                                             batch_configs=batch_configs)
            if not job_id:
                log.error('Failed to trigger gear %s for  %s/%s',
                          batch_configs.gear_name, group_id, project_lbl)
                continue

            log.info('Gear %s queued for %s/%s - Job ID %s',
                     batch_configs.gear_name, group_id, project_lbl, job_id)
            jobs_list.append(job_id)

        check_batch_run_status(proxy,
                               jobs_list=jobs_list,
                               failed_list=failed_list)

        # clear the jobs list
        # all the jobs in current batch are finished when it gets to this point
        jobs_list.clear()

        batch = get_batch(centers=centers, batch_size=batch_configs.batch_size)

    if len(failed_list) > 0:
        log.error('Failed %s ingest to accepted copy jobs: %s',
                  len(failed_list), str(failed_list))


def get_centers_to_batch(proxy: FlywheelProxy, center_ids: List[str],
                         time_interval: int, gear_name: str) -> List[str]:
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
        search_str = f'parents.group={center},state=complete,gear_info.name={gear_name}'
        job = proxy.find_job(search_str, sort='created:desc')
        if job and (today - job.transitions['complete'].date()  # type: ignore
                    ) <= timedelta(days=time_interval):
            continue

        centers_to_copy.append(center)

    return centers_to_copy


def run(*, proxy: FlywheelProxy, centers: List[str], time_interval: int,
        batch_configs: BatchRunInfo, dry_run: bool):
    """Runs the ingest to accepted transfer process.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        time_interval: time interval in days between the runs (input -1 to ignore)
        batch_configs: configurations for batch run
        dry_run: whether to do a dry run
    """

    centers_to_batch = get_centers_to_batch(
        center_ids=centers,
        proxy=proxy,
        time_interval=time_interval,
        gear_name=batch_configs.gear_name) if time_interval > 0 else centers

    minheap: List[Element] = []
    for center_id in centers_to_batch:
        try:
            source_project = proxy.lookup(
                f"{center_id}/{batch_configs.source}")
            target_project = proxy.lookup(
                f"{center_id}/{batch_configs.target}"
            ) if batch_configs.target else source_project

            count_files = (batch_configs.batch_mode == 'files')
            if not count_files or source_project.stats.number_of.acquisition_files > 0:
                heappush(
                    minheap,
                    Element(source=source_project,
                            target=target_project,
                            count_files=count_files))
                log.info('Center %s added to batch pool', center_id)
        except ApiException as error:
            log.error('Error occurred for %s: %s', center_id, str(error))
            continue

    if not len(minheap) > 0:
        log.info('No projects matched with the specified batch configs')
        return

    log.info('Number of projects to run gear %s: %s', batch_configs.gear_name,
             len(minheap))

    if dry_run:
        log.info('dry run, not running the gear')
        return

    schedule_batch_copy(proxy=proxy,
                        centers=minheap,
                        batch_configs=batch_configs)
