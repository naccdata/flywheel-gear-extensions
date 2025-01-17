"""Defines the Form Scheduler.

1. Pulls the current list of project files with the specified
   queue tags and adds them to processing queues for each module
   sorted by file timestamp
2. Process the queues in a round robin
    a. Check whether there are any submission pipelines running/pending;
       if so, wait for them to finish
    b. Pull the next CSV from the queue and clear queue tags
    c. Trigger the submission pipeline
    d. Wait for the triggered submission pipeline to finish
    e. Send email to user that the submission pipeline is complete
    f. Move to next queue
3. Repeat 2) until all queues are empty
4. Repeat from the beginning until there are no more files to be queued
"""
import logging
from typing import List, Optional

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import trigger_gear
from inputs.parameter_store import URLParameter
from jobs.job_poll import JobPoll
from notifications.email import EmailClient

from .email_user import send_email
from .form_scheduler_queue import FormSchedulerQueue

log = logging.getLogger(__name__)


def wait_for_submission_pipeline(proxy: FlywheelProxy,
                                 search_str: str) -> None:
    """Wait for the submission pipeline to finish executing before continuing.

    Args:
        proxy: the proxy for the Flywheel instance
        search_str: The search string to search for the submission pipeline
    """
    running = True
    while running:
        job = proxy.find_job(search_str)
        if job:
            log.info(f"A submission pipeline with current job {job.id} is " +
                     "running, waiting for completion")
            # at least for now we don't really care about the state
            # of other submission pipelines, we just wait for it to finish
            JobPoll.poll_job_status(job)
        else:
            running = False


def run(*,
        proxy: FlywheelProxy,
        queue: FormSchedulerQueue,
        project_id: str,
        submission_pipeline: List[str],
        email_client: Optional[EmailClient] = None,
        portal_url: Optional[URLParameter] = None):
    """Runs the Form Scheduler process.

    Args:
        proxy: the proxy for the Flywheel instance
        queue: The FormSchedulerQueue which handles the queues
        project_id: The project ID
        submission_pipeline: List of gear names representing the submission
            pipeline
        email_client: EmailClient to send emails from
        portal_url: The portal URL
    """
    project = proxy.get_project_by_id(project_id)
    if not project:
        raise GearExecutionError(f"Cannot find project with ID {project_id}")

    # search string to use for looking for running submission pipelines
    search_str = JobPoll.generate_search_string(
        project_ids_list=[project_id],
        gears_list=submission_pipeline,
        states_list=['running', 'pending'])
    log.info("Starting Form Scheduler queue")

    # 1. Pull the current list of files
    num_files = -1
    while num_files != 0:
        # force a project reload with each outer loop
        project = project.reload()
        num_files = queue.add_files(project)
        log.info(f"Pulled {num_files} queued files, beginning queue process")

        # 2. Process queue in round robin
        while not queue.empty():
            # grab the next subqueue with files in it in the round robin
            module, subqueue = queue.next_queue()
            if not subqueue:
                continue

            # a. Check if any submission pipelines are already running for
            #    this project. If one is found, wait for it to finish before continuing.
            #    This should actually not happen as it would mean that this gear
            #    instance is not the owner/trigger of this submission pipeline,
            #    but left in as a safeguard
            wait_for_submission_pipeline(proxy, search_str)

            # b. Pull the next CSV from queue and clear the queue tags
            file = subqueue.pop(0)
            for tag in queue.queue_tags:
                file.delete_tag(tag)

            # need to reload else the next gear may add the same queue tags back in
            # causing an infinite loop
            file = file.reload()

            # c. Trigger the submission pipeline.
            #    Here's where it isn't actually parameterized - we assume that
            #    the first gear is the file-validator regardless, and passes
            #    the corresponding inputs + uses the default configuration
            #    If the first gear changes and has different inputs/needs updated
            #    configurations, this may break as a result and will need to be updated
            #    Maybe we should check that the first gear is always the file-validator?

            log.info(
                f"Kicking off {submission_pipeline[0]} for {file.name}, " +
                f"module {module}")

            validation_schema = project.get_file(f'{module}-schema.json')
            if not validation_schema:
                raise GearExecutionError(
                    f"Missing validation schema for {module}")

            inputs = {
                "input_file": file,
                "validation_schema": validation_schema
            }
            trigger_gear(proxy=proxy,
                         gear_name=submission_pipeline[0],
                         inputs=inputs)

            # d. wait for the above submission pipeline to finish
            wait_for_submission_pipeline(proxy, search_str)

            # e. send email to user who uploaded the file that their
            #    submission pipeline has completed
            if email_client and file.origin.type == 'user':
                send_email(proxy=proxy,
                           email_client=email_client,
                           file=file,
                           project=project,
                           portal_url=portal_url)  # type: ignore

        # 3. repeat until all queues empty

    # 4. Repeat from beginning (pulling files) until no more files are found

    log.info("No more queued files to process, exiting Form Scheduler gear")
