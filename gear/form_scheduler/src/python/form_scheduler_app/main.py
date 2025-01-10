"""Defines the Form Scheduler.

1. Pulls the current list of project files with the specified
   queue tags and adds them to processing queues for each module
   sorted by file timestamp
2. Process the queues in round robin, with the prioritized modules
   analyzed to completion first
    a. Check whether there are any submission pipelines running/pending.
       If there are, exit gear, no need to spin up another instance.
    b. If none found, send an email notification to the user(s) who uploaded
       the original file(s) to let them know their file is in the queue
    c. Pull the next CSV in queue and trigger the submission pipeline
    d. Remove the queue tags from the file
    e. Move to next queue
3. Repeat a-e until all queues are empty
4. Repeat from the beginning
"""
import logging
import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

from flywheel import Project
from flywheel.models.file_entry import FileEntry
from flywheel.models.job_state import JobState  # type: ignore
#from flywheel.models.origin_type import OriginType
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import trigger_gear
from jobs.job_poll import JobPoll
from notifications.email import EmailClient, create_ses_client

MODULE_PATTERN = re.compile(r"^.+-([a-zA-Z]+)(\..+)$")
log = logging.getLogger(__name__)


class QueueAlertTemplateModel(BaseModel):
    """Queue alert template model"""
    project: str
    filename: str
    email_address: str


class FormSchedulerQueue:
    """Class to define a queue for each accepted module,
    with prioritization allowed.
    """

    def __init__(self,
                 proxy: FlywheelProxy,
                 module_order: List[str],
                 queue_tags: List[str],
                 source_email: Optional[str] = None) -> None:
        """Initializer.
        Args:
            proxy: the proxy for the Flywheel instance
            module_order: The modules and the order to process them in
            queue_tags: The queue tags to filter project files for
                to determine which need to be queued
            prioritized_modules: Prioritized modules; will
                go first in the round robin ordering
            source_email: Source email - if provided, will send emails
        """
        self.__proxy = proxy
        self.__module_order = module_order
        self.__index = -1
        self.__queue_tags = set(queue_tags)  # make set for comparison later

        # if sending emails, set up client
        self.__email_client = EmailClient(client=create_ses_client(),
                                          source=source_email) \
            if source_email else None

        self.queue: Dict[str, List[FileEntry]] = {k: [] for k in self.__module_order}

    def add_files(self, project_id: str) -> Tuple[Project, int]:
        """Add the files (filtered by queue tags) to queue.

        Args:
            project_id: Project ID to pull queue files from
        Returns:
            The project that was pulled from and the number of files added
        """
        # grab each time to make sure it's refreshed
        project = self.__proxy.get_project_by_id(project_id)
        if not project:
            raise GearExecutionError(f"Cannot find project with ID {project_id}")

        files = [x for x in project.files if self.__queue_tags.issubset(set(x.tags))]
        num_files = 0

        # grabs files in the format *-<module>.<ext>
        for file in files:
            match = re.search(MODULE_PATTERN, file.name.lower())
            # skip over files that do not match regex - form-screening gear should
            # check this so these should just be files that were incorrectly tagged
            # by something else
            if not match:
                continue

            module = match.group(1)
            ext = match.group(2)
            if ext not in ['.csv', '.json']:
                continue

            # add to queue and maybe send email
            # TODO: These need to be set up in AWS
            self.queue[module].append(file)
            num_files += 1
            # if self.__email_client and file.origin.type == OriginType.USER:
            #     owner = file.origin.id
            #     template_data = QueueAlertTemplateModel(
            #         project=project.label,
            #         file=file.name,
            #         email_address=owner)

            #     self.__email_client.send(configuration_set_name='TODO',
            #                              destination=DestinationModel(
            #                                 to_addresses=owner),
            #                              template='TODO',
            #                              template_data=template_data)

        # sort each queue by last modified date
        for subqueue in self.queue.values():
            subqueue.sort(key=lambda file: file.modified)

        return project, num_files

    def next_queue(self) -> Tuple[str, List[FileEntry]]:
        """Returns the next queue in the round robin.

        Returns:
            Tuple with the module name and its corresponding
            queue to be processed.
        """
        if self.__index + 1 >= len(self.__module_order):
            self.__index = 0
        else:
            self.__index += 1

        module = self.__module_order[self.__index]
        return module, self.queue[module]

    def empty(self) -> bool:
        """Returns whether or not the queue is empty.

        Returns:
            True if the queue is empty, False otherwise.
        """
        return all(not x for x in self.queue.values())

def run(*,
        proxy: FlywheelProxy,
        queue: FormSchedulerQueue,
        project_id: str,
        submission_pipeline: List[str]):
    """Runs the Form Scheduler process.

    Args:
        proxy: the proxy for the Flywheel instance
        queue: The FormSchedulerQueue which handles the queues
        project_id: The project ID
        submission_pipeline: List of gear names representing the submission
            pipeline
    """
    # search string to use for looking for running submission pipelines
    search_str = f'parents.project={project_id},' \
        + f'gear_info.name=|{submission_pipeline},' \
        + f'state=|{[JobState.PENDING, JobState.RUNNING]}'

    log.info("Starting Form Scheduler queue")

    # 1. Pull the current list of files
    num_files = -1
    while num_files != 0:
        project, num_files = queue.add_files(project_id)
        log.info(f"Pulled {num_files} queued files, beginning queue process")

        # 2. Process queue in round robin
        while not queue.empty():
            # grab the next subqueue with files in it in the round robin
            module, subqueue = queue.next_queue()
            if not subqueue:
                continue

            # a. Check if any submission pipelines are running for this project
            #    if one is found, wait for it to finish before continuing
            running = True
            while running:
                job = proxy.find_job(search_str)
                if job:
                    # at least for now we don't really care about the state
                    # of other submission pipelines, we just wait for it to finish
                    JobPoll.poll_job_status(job)
                else:
                    running = False

            # b. Send email notification (TODO)

            # c. Pull the next CSV from queue and trigger submission pipeline
            #    Here's where it isn't actually parameterized - it is assumed that
            #    the first gear is the file-validator regardless, and passes
            #    the corresponding inputs + uses the default configuration
            #    If the first gear changes and has different inputs/needs updated
            #    configurations, this may break as a result and will need to be updated
            #    Maybe we should check that the first gear is always this?
            inputs = {
                "input_file": subqueue.pop(0),
                "validation_schema": project.get_file(f'{module}-schema.json')
            }
            trigger_gear(proxy=proxy,
                         gear_name=submission_pipeline[0],
                         inputs=inputs)

        # 3. repeat until all queues empty

    # 4. Repeat from beginning (pulling files) until no more files are found

    log.info("No matter files to process, exiting Form Scheduler gear")
