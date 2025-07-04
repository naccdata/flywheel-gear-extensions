"""Defines batch scheduling."""

import logging
import time
from datetime import date, timedelta
from functools import total_ordering
from heapq import heappop, heappush
from typing import List, Optional, Tuple

from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_trigger import BatchRunInfo, trigger_gear
from jobs.job_poll import JobPoll
from notifications.email import EmailClient, create_ses_client

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
        return (
            self.source.stats.number_of.acquisition_files
            < value.source.stats.number_of.acquisition_files
        )

    @property
    def count(self) -> int:
        if self.count_files:
            return self.source.stats.number_of.acquisition_files

        return 1


def trigger_gear_for_center(
    proxy: FlywheelProxy, batch_configs: BatchRunInfo, center: Element
) -> Optional[str]:
    """Trigger the gear for specified center.

    Args:
        proxy: Flywheel proxy
        batch_configs: batch run configs
        center: center information

    Returns:
        Optional[str]: gear job id or None
    """

    gear_configs = batch_configs.get_gear_configs(
        source=center.source.id, target=center.target.id
    )
    if not gear_configs:
        log.error("Error in retrieving gear configs for center %s", center.source.label)
        return None

    job_id = trigger_gear(
        proxy=proxy,
        gear_name=batch_configs.gear_name,
        config=gear_configs,
        inputs={},
        destination=center.source,
    )

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


def check_batch_run_status(
    proxy: FlywheelProxy, jobs_list: List[str], failed_list: List[str]
):
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


def schedule_batch_copy(
    proxy: FlywheelProxy, centers: List[Element], batch_configs: BatchRunInfo
) -> Optional[List[str]]:
    """Schedule the centers in batches depending on the batch mode and batch
    size.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        batch_configs: batch run configurations

    Returns:
        Optional[List[str]]: list of failed job IDs if any
    """

    failed_list: List[str] = []
    jobs_list: List[str] = []
    batch = get_batch(centers=centers, batch_size=batch_configs.batch_size)
    while len(batch) > 0:
        log.info("Scheduling %s on %s centers", batch_configs.gear_name, len(batch))
        for center in batch:
            group_id = center.source.group
            project_lbl = center.source.label
            job_id = trigger_gear_for_center(
                proxy=proxy, center=center, batch_configs=batch_configs
            )
            if not job_id:
                log.error(
                    "Failed to trigger gear %s for  %s/%s",
                    batch_configs.gear_name,
                    group_id,
                    project_lbl,
                )
                continue

            log.info(
                "Gear %s queued for %s/%s - Job ID %s",
                batch_configs.gear_name,
                group_id,
                project_lbl,
                job_id,
            )
            jobs_list.append(job_id)

        check_batch_run_status(proxy, jobs_list=jobs_list, failed_list=failed_list)

        # clear the jobs list
        # all the jobs in current batch are finished when it gets to this point
        jobs_list.clear()
        log.info("Number of remaining centers: %s", len(centers))
        batch = get_batch(centers=centers, batch_size=batch_configs.batch_size)

    if len(failed_list) > 0:
        log.error(
            "Retrying %s failed gear jobs: %s", len(failed_list), str(failed_list)
        )
        new_jobs, failed_jobs = retry_failed_jobs(
            proxy=proxy, failed_ids=failed_list, batch_size=batch_configs.batch_size
        )
        if new_jobs:
            check_batch_run_status(
                proxy=proxy, jobs_list=new_jobs, failed_list=failed_jobs
            )

        return failed_jobs

    return None


def get_centers_to_batch(
    proxy: FlywheelProxy, center_ids: List[str], time_interval: int, gear_name: str
) -> List[str]:
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
        search_str = f"parents.group={center},state=complete,gear_info.name={gear_name}"
        job = proxy.find_job(search_str, sort="created:desc")
        if job and (
            today - job.transitions["complete"].date()  # type: ignore
        ) <= timedelta(days=time_interval):
            continue

        centers_to_copy.append(center)

    return centers_to_copy


def retry_failed_jobs(
    proxy: FlywheelProxy, failed_ids: List[str], batch_size: int
) -> Tuple[List[str], List[str]]:
    """Retry the failed jobs.

    Args:
        proxy: Flywheel proxy object
        failed_ids: List of failed job IDs to retry
        batch_size: Number of jobs to retry in one batch

    Returns:
        Tuple[List[str], List[str]]: List of new job IDs, List of failed retries
    """
    new_jobs: List[str] = []
    failed_retries: List[str] = []
    num_retried = 0
    wait_time = (batch_size / 5) * 60
    for failed_id in failed_ids:
        new_job = proxy.retry_job(failed_id)
        if new_job:
            new_jobs.append(new_job)
            num_retried += 1
        else:
            failed_retries.append(failed_id)

        if num_retried % batch_size == 0:
            time.sleep(wait_time)  # wait before starting the next batch

    return new_jobs, failed_retries


def send_email(
    sender_email: str, target_emails: List[str], gear_name: str, failed_count: int
) -> None:
    """Send a raw email notifying target emails of the error.

    Args:
        sender_email: The sender email
        target_emails: The target email(s)
        gear_name: Name of the gear triggered by scheduler
        failed_count: Number of failed gear jobs
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    subject = f"Batch Scheduler - One or more {gear_name} gear jobs failed"
    body = (
        f"Number of {gear_name} gear jobs failed: {failed_count}.\n"
        + "Check the batch-scheduler error log for the list of failed jobs.\n\n"
    )

    client.send_raw(destinations=target_emails, subject=subject, body=body)


def run(
    *,
    proxy: FlywheelProxy,
    centers: List[str],
    time_interval: int,
    batch_configs: BatchRunInfo,
    sender_email: str,
    target_emails: List[str],
    dry_run: bool,
):
    """Runs the batch scheduling process.

    Args:
        proxy: Flywheel proxy
        centers: list of centers to copy data
        time_interval: time interval in days between the runs (input -1 to ignore)
        batch_configs: configurations for batch run
        sender_email: The sender email for error notification
        target_emails: The target email(s) to be notified
        dry_run: whether to do a dry run
    """

    centers_to_batch = (
        get_centers_to_batch(
            center_ids=centers,
            proxy=proxy,
            time_interval=time_interval,
            gear_name=batch_configs.gear_name,
        )
        if time_interval > 0
        else centers
    )

    minheap: List[Element] = []
    for center_id in centers_to_batch:
        try:
            source_project = proxy.lookup(f"{center_id}/{batch_configs.source}")
            target_project = (
                proxy.lookup(f"{center_id}/{batch_configs.target}")
                if batch_configs.target
                else source_project
            )

            count_files = batch_configs.batch_mode == "files"
            if not count_files or source_project.stats.number_of.acquisition_files > 0:
                heappush(
                    minheap,
                    Element(
                        source=source_project,
                        target=target_project,
                        count_files=count_files,
                    ),
                )
                log.info("Center %s added to batch pool", center_id)
        except ApiException as error:
            log.error("Error occurred for %s: %s", center_id, str(error))
            continue

    if not len(minheap) > 0:
        log.info("No projects matched with the specified batch configs")
        return

    log.info(
        "Number of projects to run gear %s: %s", batch_configs.gear_name, len(minheap)
    )

    if dry_run:
        log.info("dry run, not running the gear")
        return

    failed_jobs = schedule_batch_copy(
        proxy=proxy, centers=minheap, batch_configs=batch_configs
    )

    if failed_jobs and len(failed_jobs) > 0:
        log.error(
            "List of failed %s gear jobs: %s", batch_configs.gear_name, failed_jobs
        )
        log.error(
            "Number of failed %s gear jobs: %s",
            batch_configs.gear_name,
            len(failed_jobs),
        )
        send_email(
            sender_email=sender_email,
            target_emails=target_emails,
            gear_name=batch_configs.gear_name,
            failed_count=len(failed_jobs),
        )
