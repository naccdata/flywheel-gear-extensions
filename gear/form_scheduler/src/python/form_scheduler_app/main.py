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

from configs.ingest_configs import PipelineConfigs

from .form_scheduler_queue import FormSchedulerQueue

log = logging.getLogger(__name__)


def run(*, queue: FormSchedulerQueue, pipeline_configs: PipelineConfigs):
    """Runs the Form Scheduler process.

    Args:
        queue: The FormSchedulerQueue which handles the queues
        pipeline_configs: Form pipeline configurations
    """
    num_files = -1
    while num_files != 0:
        num_files = 0  # reset counter for next iteration
        # Pull and queue the tagged files for each pipeline
        # Pipelines are processed in order they are specified in the configs file
        for pipeline in pipeline_configs.pipelines:
            num_files += queue.queue_files_for_pipeline(pipeline)

        # Process the subqueues for each pipeline until all pipeline queues are empty
        queue.process_pipeline_queues()

        # Repeat from beginning (pulling files) until no more matching files are found

    log.info("No more queued files to process, exiting Form Scheduler gear")
