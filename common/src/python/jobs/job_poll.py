"""Handles functionality related to watching/polling jobs."""
import logging
import time
from typing import List, Optional

from flywheel.models.job import Job
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError

log = logging.getLogger(__name__)


class JobPoll:

    @staticmethod
    def poll_job_status(job: Job) -> str:
        """Check for the completion status of a gear job.

        Args:
            job: Flywheel Job object

        Returns:
            str: job completion status
        """

        while job.state in ['pending', 'running']:
            time.sleep(30)
            job = job.reload()

        if job.state == 'failed':
            time.sleep(5)  # wait to see if the job gets retried
            job = job.reload()

        if job.state == 'completed':
            time.sleep(5)  # give buffer between gear triggers

        log.info('Job %s finished with status: %s', job.id, job.state)

        return job.state

    @staticmethod
    def poll_job_status_by_id(proxy: FlywheelProxy, job_id: str) -> str:
        """Check for the completion status of a gear job.

        Args:
            proxy: the FlywheelProxy
            job_id: Flywheel job ID

        Returns:
            str: job completion status
        """
        job = proxy.get_job_by_id(job_id)
        if not job:
            raise GearExecutionError(f"Unable to find job: {job_id}")

        return JobPoll.poll_job_status(job)

    @staticmethod
    def is_job_complete(proxy: FlywheelProxy, job_id: str) -> bool:
        """Checks the status of the given job.

        Args:
            proxy: the FlywheelProxy
            job_id: Flywheel job ID

        Returns:
            bool: True if job successfully complete, else False
        """
        status = JobPoll.poll_job_status_by_id(job_id)
        max_retries = 3  # maximum number of retries in Flywheel
        retries = 1
        while status == 'retried' and retries <= max_retries:
            new_job = proxy.find_job(f'previous_job_id="{job_id}"')
            if not new_job:
                log.error('Cannot find a retried job with previous_job_id=%s',
                          job_id)
                break
            job_id = new_job.id
            retries += 1
            status = JobPoll.poll_job_status(new_job)

        return status == 'completed'

    @staticmethod
    def generate_search_string(project_ids_list: Optional[List[str]] = None,
                               gears_list: Optional[List[str]] = None,
                               states_list: Optional[List[str]] = None) -> str:
        """Generates the search string for polling jobs.

        Args:
            project_ids_list: The list of project IDs to filter on
            gears_list: The list of gears to filter on
            states_list: The list of states to filter on
        Returns:
            The formatted job search string
        """
        result = ''
        if states_list:
            result = f'state=|[{",".join(states_list)}]'
        if gears_list:
            result = f'gear_info.name=|[{",".join(gears_list)}],{result}'
        if project_ids_list:
            result = f'parents.project=|[{",".join(project_ids_list)}],{result}'

        return result.rstrip(',')
