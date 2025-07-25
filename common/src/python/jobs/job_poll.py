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

        while job.state in ["pending", "running"]:
            time.sleep(30)
            job = job.reload()

        if job.state == "failed":
            time.sleep(5)  # wait to see if the job gets retried
            job = job.reload()

            if job.state == "failed" and job.retried is not None:
                log.info("Job %s was retried", job.id)
                return "retried"

        log.info("Job %s finished with status: %s", job.id, job.state)

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
        status = JobPoll.poll_job_status_by_id(proxy, job_id)
        max_retries = 3  # maximum number of retries in Flywheel
        retries = 1
        while status == "retried" and retries <= max_retries:
            new_job = proxy.find_job(f'previous_job_id="{job_id}"')
            if not new_job:
                log.error("Cannot find a retried job with previous_job_id=%s", job_id)
                break
            job_id = new_job.id
            retries += 1
            status = JobPoll.poll_job_status(new_job)

        return status == "complete"

    @staticmethod
    def generate_search_string(
        project_ids_list: Optional[List[str]] = None,
        gears_list: Optional[List[str]] = None,
        states_list: Optional[List[str]] = None,
    ) -> str:
        """Generates the search string for polling jobs.

        Args:
            project_ids_list: The list of project IDs to filter on
            gears_list: The list of gears to filter on
            states_list: The list of states to filter on
        Returns:
            The formatted job search string
        """
        result = ""
        if states_list:
            result = f'state=|[{",".join(states_list)}]'
        if gears_list:
            result = f'gear_info.name=|[{",".join(gears_list)}],{result}'
        if project_ids_list:
            result = f'parents.project=|[{",".join(project_ids_list)}],{result}'

        return result.rstrip(",")

    @staticmethod
    def wait_for_pipeline(proxy: FlywheelProxy, search_str: str) -> None:
        """Wait for a pipeline to finish executing before continuing.

        Args:
            proxy: the proxy for the Flywheel instance
            search_str: The search string to search for the pipeline
        """
        running = True
        while running:
            job = proxy.find_job(search_str)
            if job:
                log.info(
                    f"A pipeline with current job {job.id} is "
                    + "running, waiting for completion"
                )
                # at least for now we don't really care about the state
                # of other submission pipelines, we just wait for it to finish
                JobPoll.poll_job_status(job)
            else:
                running = False

    @classmethod
    def is_another_gear_instance_running(
        cls, *, proxy: FlywheelProxy, gear_name: str, project_id: str, current_job: str
    ) -> bool:
        """Find whether another instance of the specified gear is running
        Args:
            proxy: the proxy for the Flywheel instance
            gear_name: gear name to check
            project_id: Flywheel project to check
            current_job: current job id

        Returns:
            bool: True if another job found, else False
        """
        search_str = JobPoll.generate_search_string(
            project_ids_list=[project_id],
            gears_list=[gear_name],
            states_list=["running", "pending"],
        )

        matched_jobs = proxy.find_jobs(search_str)
        if len(matched_jobs) > 1:
            return True

        return current_job != matched_jobs[0].id
