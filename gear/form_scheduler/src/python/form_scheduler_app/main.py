"""Defines the Form Scheduler.

1. Pull and queue the tagged files for each pipeline by module sorted by file timestamp
2. Pipelines are processed in the order they are listed in the pipeline configs file
   For each pipeline, process the module subqueues
3. Modules are processed in the order they are listed in pipeline configs
   Move to next module subqueue,
    a. Check whether there are any pipeline gears running/pending;
       if so, wait for them to finish
    b. Pull the next file from the subqueue and clear queue tags
    c. Trigger the starting gear for the pipeline on the pulled file
    d. Wait for the triggered pipeline to finish
    e. Send email to user that the submission pipeline is complete
    f. Repeat 3a - 3e until current subqueue is empty
   Repeat 3a - 3e until all subqueues are empty for the current pipeline
4. Move to next pipeline, and repeat 3)
5. Repeat from the beginning until there are no more files to be queued
"""

import logging
from typing import Optional

from configs.ingest_configs import PipelineConfigs
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from inputs.parameter_store import URLParameter
from notifications.email import EmailClient

from .form_scheduler_queue import FormSchedulerQueue

log = logging.getLogger(__name__)


def run(
    *,
    proxy: FlywheelProxy,
    project_id: str,
    pipeline_configs: PipelineConfigs,
    email_client: Optional[EmailClient] = None,
    portal_url: Optional[URLParameter] = None,
):
    """Runs the Form Scheduler process.

    Args:
        proxy: the proxy for the Flywheel instance
        queue: The FormSchedulerQueue which handles the queues
        project_id: The project ID
        pipeline_configs: Form pipeline configurations
        email_client: EmailClient to send emails from
        portal_url: The portal URL
    """

    project = proxy.get_project_by_id(project_id)
    if not project:
        raise GearExecutionError(f"Cannot find project with ID {project_id}")
    project_adaptor = ProjectAdaptor(project=project, proxy=proxy)

    queue = FormSchedulerQueue(
        proxy=proxy,
        project=project_adaptor,
        pipeline_configs=pipeline_configs,
        email_client=email_client,
        portal_url=portal_url,
    )

    num_files = -1
    while num_files != 0:
        # force a project reload with each outer loop
        project = project.reload()

        num_files = 0  # reset counter for next iteration
        # Pull and queue the tagged files for each pipeline
        # Pipelines are processed in order they are specified in the configs file
        for pipeline in pipeline_configs.pipelines:
            num_files += queue.queue_files_for_pipeline(
                project=project, pipeline=pipeline
            )

        # Process the subqueues for each pipeline until all pipeline queues are empty
        queue.process_pipeline_queues()

        # Repeat from beginning (pulling files) until no more matching files are found

    log.info("No more queued files to process, exiting Form Scheduler gear")
