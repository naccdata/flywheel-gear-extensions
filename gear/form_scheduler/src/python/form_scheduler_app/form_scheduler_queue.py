"""Defines the Form Scheduler Queue.

This module implements a queue-based system for scheduling and
processing form pipelines in Flywheel. It manages multiple pipelines
(submission, finalization) and ensures files are processed in the
correct order with proper coordination between pipeline stages.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from json.decoder import JSONDecodeError
from typing import Callable, Dict, List, Optional, Tuple

from configs.ingest_configs import Pipeline, PipelineConfigs, PipelineType
from data.dataview import ColumnModel, make_builder
from event_capture.event_capture import VisitEventCapture
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import (
    set_gear_inputs,
    trigger_gear,
)
from inputs.parameter_store import URLParameter
from jobs.job_poll import JobPoll
from nacc_common.qc_report import QCTransformerError
from notifications.email import EmailClient
from pydantic import BaseModel, ConfigDict, ValidationError

from form_scheduler_app.email_user import send_email
from form_scheduler_app.event_accumulator import EventAccumulator

# Regex pattern to extract module name from filenames
# Matches filenames like "ptid-MODULE.csv" and captures the module name
MODULE_PATTERN = re.compile(r"^.*-([a-zA-Z1-9]+)(\..+)$")

log = logging.getLogger(__name__)


class PipelineQueue(BaseModel):
    """Class to represent a file queue for a given pipeline, with subqueues
    defined for each module accepted for the pipeline.

    The queue uses a round-robin approach to process files from different
    modules fairly, preventing any single module from monopolizing processing.

    Attributes:
        index: Current position in the round-robin rotation (-1 = not started)
        pipeline: Pipeline configuration defining accepted modules and tags
        subqueues: Dictionary mapping module names to their file queues
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: int = -1
    pipeline: Pipeline
    subqueues: Dict[str, List[FileEntry]]

    @property
    def name(self) -> PipelineType:
        return self.pipeline.name

    @property
    def tags(self) -> List[str]:
        return self.pipeline.tags

    @property
    def modules(self) -> List[str]:
        return self.pipeline.modules

    @property
    def extensions(self) -> List[str]:
        return self.extensions

    def add_file_to_subqueue(self, module: str, file: FileEntry) -> bool:
        """Add the file to given module subqueue.

        Args:
            module: module name
            file: file to add

        Returns:
            True if file successfully queued
        """

        # skip over files that do not match the accepted modules for the pipeline
        if module.upper() not in self.modules:
            log.warning(
                "File %s is not in the accepted modules %s for pipeline `%s`",
                file.name,
                self.modules,
                self.name,
            )
            return False

        self.subqueues[module.upper()].append(file)
        return True

    def sort_subqueues(self):
        """Sort each queue by ascending order of file modified date.

        This ensures older files are processed first, maintaining FIFO
        ordering within each module's subqueue.
        """
        for subqueue in self.subqueues.values():
            subqueue.sort(key=lambda file: file.modified)

    def next_queue(self) -> Tuple[str, List[FileEntry]]:
        """Returns the next module queue for the pipeline using round-robin.

        Advances the index to the next module in a circular fashion,
        ensuring fair processing across all modules.

        Returns:
            Tuple with the module name and its corresponding
            queue to be processed.
        """
        # Circular increment: wraps around to 0 after reaching last module
        self.index = (self.index + 1) % len(self.modules)
        module = self.modules[self.index]
        return module, self.subqueues[module]

    def empty(self) -> bool:
        """Returns whether or not all the subqueues are empty.

        Returns:
            True if all subqueues are empty, False otherwise.
        """
        return all(not x for x in self.subqueues.values())


class PipelineQueueBuilder(ABC):
    """Abstract base class for building pipeline queues.

    Different pipeline types (submission, finalization) have different
    strategies for finding and organizing files. This builder pattern
    allows each pipeline type to implement its own file discovery logic.
    """

    def __init__(self, pipeline: Pipeline, queues: dict[str, list[FileEntry]]) -> None:
        self.__pipeline = pipeline
        self.__queue = PipelineQueue(pipeline=pipeline, subqueues=queues)

    @property
    def name(self) -> PipelineType:
        return self.__pipeline.name

    @property
    def tags(self) -> List[str]:
        return self.__pipeline.tags

    @property
    def modules(self) -> List[str]:
        return self.__pipeline.modules

    @property
    def extensions(self) -> List[str]:
        return self.__pipeline.extensions

    def queue(self) -> PipelineQueue:
        return self.__queue

    def add_pipeline_files(self, project: ProjectAdaptor) -> int:
        """Adds files from the project matching the pipeline to the queues.

        This method orchestrates the file discovery and queueing process:
        1. Find matching files using pipeline-specific logic
        2. Add files to appropriate module subqueues
        3. Sort subqueues by file modification time

        Args:
          project: the project

        Returns:
          Number of files successfully added to queues
        """
        # Use pipeline-specific logic to find matching files
        module_map = self.find_matching_visits_for_the_pipeline(project)
        if not module_map:
            log.info(
                f"No matching files for pipeline `{self.__pipeline.name}` "
                f"with tags: {self.__pipeline.tags} and "
                f"extensions: {self.__pipeline.extensions}"
            )
            return 0

        # Add each file to its module's subqueue
        num_files = 0
        for module, files in module_map.items():
            for file in files:
                added = self.__queue.add_file_to_subqueue(module, file)
                if added:
                    num_files += 1

        # Sort all subqueues by file modification time (oldest first)
        self.__queue.sort_subqueues()

        return num_files

    def file_match(self, file_entry: FileEntry) -> bool:
        return self.__pipeline.file_match(file_entry)

    @abstractmethod
    def find_matching_visits_for_the_pipeline(
        self, project: ProjectAdaptor
    ) -> dict[str, list[FileEntry]]:
        return {}


class SubmissionQueueBuilder(PipelineQueueBuilder):
    """Builder for submission pipeline queues.

    Submission pipelines process files at the PROJECT level. Files are
    identified by tags and extensions, with module names extracted from
    the filename pattern (e.g., "ptid-ivp.csv" -> module "ivp").
    """

    def find_matching_visits_for_the_pipeline(
        self, project: ProjectAdaptor
    ) -> dict[str, list[FileEntry]]:
        """Find project-level files matching pipeline criteria.

        Returns:
            Dictionary mapping module names to lists of matching files
        """
        # Filter project files by tags and extensions
        files = [
            file_entry for file_entry in project.files if self.file_match(file_entry)
        ]

        # Group files by module extracted from filename
        module_map: dict[str, list[FileEntry]] = defaultdict(list)
        for file in files:
            # Extract module name from filename (e.g., "ptid-uds.csv" -> "uds")
            match = re.search(MODULE_PATTERN, file.name.lower())
            if not match:
                log.warning(
                    "File %s is incorrectly tagged with one or more tags %s",
                    file.name,
                    self.tags,
                )
                continue

            module = match.group(1)
            module_map[module].append(file)
        return module_map


class FinalizationQueueBuilder(PipelineQueueBuilder):
    """Builder for finalization pipeline queues.

    Finalization pipelines process files at the ACQUISITION level. Uses
    Flywheel's DataView API to efficiently query files across multiple
    acquisitions, filtering by module labels, tags, and extensions.
    """

    def find_matching_visits_for_the_pipeline(
        self, project: ProjectAdaptor
    ) -> dict[str, list[FileEntry]]:
        """Find acquisition-level files using DataView API.

        Uses Flywheel's DataView to query files across acquisitions,
        which is more efficient than iterating through all acquisitions.

        Args:
            project: Flywheel project container

        Returns:
            Dictionary mapping module names to lists of matching files
        """

        # TODO: Find a way to search multiple tags
        # Checked with FW and multi tag OR search currently doesn't work
        # finalization pipeline currently only has one tag, so no issue for now
        if len(self.tags) > 1:
            raise GearExecutionError(
                f"Cannot support searching for multiple file tags {self.tags}"
            )

        modules = self.modules
        tag = self.tags[0]
        extensions = self.extensions

        # Build regex pattern to match any of the accepted file extensions
        # e.g., [".json", ".csv"] -> "^.*\.json$|^.*\.csv$"
        filename_pattern = ""
        filename_pattern += "|".join(f"^.*\\{ext}$" for ext in extensions)

        # Create DataView to query acquisitions with matching files
        builder = make_builder(
            label=f"Participant visits with tags {tag}",
            description="List of finalized visits for the module",
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(data_key="acquisition.label", label="module"),
            ],
            container="acquisition",
            # Filter: acquisition label must be in modules list AND file must have tag
            filter_str=f"acquisition.label=|[{','.join(modules)}],file.tags={tag}",
            missing_data_strategy="drop-row",
        )

        # Apply filename pattern filter
        builder.file_filter(value=filename_pattern, regex=True)
        # Need to set the container again (should be same as "container" above)
        # If only file_filter is set, FW reports following error:
        # ValueError: Both file_container and file_filter are required
        builder.file_container("acquisition")
        view = builder.build()

        # Execute DataView query and parse results
        module_map: dict[str, list[FileEntry]] = defaultdict(list)
        with project.read_dataview(view=view) as resp:
            try:
                result = json.load(resp)
            except JSONDecodeError as error:
                log.error(
                    "Error in loading dataview %s on container %s: %s",
                    view.label,
                    project.id,
                    error,
                )
                return module_map

        if not result or "data" not in result:
            return module_map

        # Group files by module from DataView results
        for visit in result["data"]:
            # Retrieve full file object using file_id
            # Note: Cannot use project.get_file() as these are acquisition-level files
            file_id = visit.get("file_id")
            if not file_id:
                log.warning(
                    "No file_id found for file %s in module %s",
                    visit.get("filename"),
                    visit.get("module"),
                )
                continue

            file = project.get_file_by_id(file_id)
            if file is None:
                log.warning(
                    "Could not retrieve file with id %s (filename: %s)",
                    file_id,
                    visit.get("filename"),
                )
                continue

            # Add file to its module's list
            module_map[visit["module"]].append(file)

        return module_map


def create_queue_builder(pipeline: Pipeline) -> Optional[PipelineQueueBuilder]:
    """Factory function to create the appropriate queue builder for a pipeline.

    Args:
        pipeline: Pipeline configuration

    Returns:
        PipelineQueueBuilder instance for the pipeline type, or None if unsupported
    """
    # Initialize empty subqueues for each module
    queues: dict[str, list[FileEntry]] = {k: [] for k in pipeline.modules}

    # Return appropriate builder based on pipeline type
    if pipeline.name == "finalization":
        return FinalizationQueueBuilder(pipeline=pipeline, queues=queues)
    if pipeline.name == "submission":
        return SubmissionQueueBuilder(pipeline=pipeline, queues=queues)
    return None


class FormSchedulerQueue:
    """Main orchestrator for scheduling and processing form pipelines.

    This class coordinates the entire pipeline processing workflow:
    1. Queues files for each configured pipeline
    2. Processes pipelines in order with proper synchronization
    3. Manages gear triggering and job polling
    4. Handles user notifications on completion

    The scheduler ensures only one pipeline runs at a time per project
    to avoid conflicts and race conditions.
    """

    def __init__(
        self,
        proxy: FlywheelProxy,
        project: ProjectAdaptor,
        pipeline_configs: PipelineConfigs,
        event_capture: VisitEventCapture,
        email_client: Optional[EmailClient] = None,
        portal_url: Optional[URLParameter] = None,
    ) -> None:
        """Initializer.

        Args:
            proxy: the proxy for the Flywheel instance
            project: Flywheel project container
            pipeline_configs: form pipeline configurations
            event_capture: VisitEventCapture for capturing visit events
            email_client: EmailClient to send emails from
            portal_url: The portal URL
        """
        self.__proxy = proxy
        self.__project = project
        self.__pipeline_configs = pipeline_configs
        self.__event_capture = event_capture
        self.__email_client = email_client
        self.__portal_url = portal_url
        self.__pipeline_queues: Dict[str, PipelineQueue] = {}

    def queue_files_for_pipeline(self, pipeline: Pipeline) -> int:
        """Queue the matching files for the given pipeline.

        Reloads the project first to pick up any new files that may have been
        added during processing.

        Args:
            pipeline: Pipeline configurations

        Returns:
            int: Number of files added to the pipeline queue
        """
        # Reload project to pick up any new files or updated attributes
        self.__project.reload()

        queue_builder = create_queue_builder(pipeline)
        if queue_builder is None:
            raise FormSchedulerError("Pipeline with name {pipeline.name} not supported")

        file_count = queue_builder.add_pipeline_files(self.__project)
        self.__pipeline_queues[pipeline.name] = queue_builder.queue()

        return file_count

    def process_pipeline_queues(self):
        """Process all queued pipelines in configured order.

        Pipelines are processed sequentially in the order defined in the
        configuration file. This ensures proper dependencies between
        pipelines (e.g., submission must complete before finalization).

        Raises:
            GearExecutionError: if problems occur while processing
        """
        # Build search string to find running/pending jobs for this project
        # Used to ensure we don't start new pipelines while others are running
        search_str = JobPoll.generate_search_string(
            project_ids_list=[self.__project.id],
            gears_list=self.__pipeline_configs.gears,
            states_list=["running", "pending"],
        )

        # Process pipelines in configured order
        for pipeline in self.__pipeline_configs.pipelines:
            # Skip pipelines with no queued files
            if pipeline.name not in self.__pipeline_queues:
                continue

            # Only capture events for finalization pipeline
            event_capture_callback = (
                self._capture_pipeline_events
                if pipeline.name == "finalization"
                else None
            )

            try:
                self._process_pipeline_queue(
                    pipeline=pipeline,
                    pipeline_queue=self.__pipeline_queues[pipeline.name],
                    job_search=search_str,
                    notify_user=pipeline.notify_user,
                    event_capture_callback=event_capture_callback,
                )
            except ValueError as error:
                raise GearExecutionError(
                    f"Failed to process pipeline `{pipeline.name}`: {error}"
                ) from error

    def _capture_pipeline_events(self, json_file: FileEntry) -> None:
        """Capture QC-pass events for a processed JSON file.

        Event capture failures are logged but don't stop pipeline processing.

        Args:
            json_file: The JSON file that was processed
        """
        try:
            event_accumulator = EventAccumulator(event_capture=self.__event_capture)
            event_accumulator.capture_events(
                json_file=json_file, project=self.__project
            )
        except (ValidationError, QCTransformerError) as error:
            # Validation errors from malformed data or transformers
            log.error(
                f"Failed to capture events for {json_file.name}: {error}",
                exc_info=True,
            )
        except Exception as error:
            # Catch any unexpected errors (network, S3, etc.)
            log.error(
                f"Unexpected error capturing events for {json_file.name}: {error}",
                exc_info=True,
            )

    def _process_pipeline_queue(
        self,
        *,
        pipeline: Pipeline,
        pipeline_queue: PipelineQueue,
        job_search: str,
        notify_user: bool,
        event_capture_callback: Optional[Callable[[FileEntry], None]] = None,
    ):
        """Process files in a pipeline queue using round-robin scheduling.

        This method implements the core pipeline processing logic:
        1. Set up gear inputs (fixed, module-specific, matched)
        2. Process each module's subqueue in round-robin fashion
        3. For each file: remove tags, trigger gear, wait for completion
        4. Send notifications if enabled

        The round-robin approach ensures fair processing across modules,
        preventing any single module from monopolizing resources.

        Args:
            pipeline: pipeline configs
            pipeline_queue: files queued for this pipeline
            job_search: lookup string to find running pipelines
            notify_user: whether to notify the user about completion
            event_capture_callback: optional callback to capture events after
                processing each file (used for finalization pipeline)
        """

        # Get the starting gear's input file configurations
        # Inputs are categorized by how they're located:
        # - fixed: project-level files with fixed names
        # - module: project-level files with module-specific names
        # - matched: the file being processed from the queue
        gear_input_info = pipeline.starting_gear.get_inputs_by_file_locator_type(
            locators=["fixed", "matched", "module"]
        )

        gear_inputs: Dict[str, FileEntry] = {}

        # Set gear inputs of type "fixed"
        # These are project-level files with fixed filenames (e.g., "centers.csv")
        if gear_input_info and "fixed" in gear_input_info:
            set_gear_inputs(
                project=self.__project,
                gear_name=pipeline.starting_gear.gear_name,
                locator="fixed",
                gear_inputs_list=gear_input_info["fixed"],
                gear_inputs=gear_inputs,
            )

        # Process all subqueues using round-robin scheduling
        while not pipeline_queue.empty():
            # Get next module subqueue in round-robin order
            module, subqueue = pipeline_queue.next_queue()
            if not subqueue:
                continue

            # Set gear inputs of type "module"
            # These are project-level files with module-specific names
            # (e.g., "ivp-definitions.csv" for module "ivp")
            if gear_input_info and "module" in gear_input_info:
                set_gear_inputs(
                    project=self.__project,
                    gear_name=pipeline.starting_gear.gear_name,
                    locator="module",
                    gear_inputs_list=gear_input_info["module"],
                    gear_inputs=gear_inputs,
                    module=module,
                )

            # a. Check if any pipelines are already running for this project
            #    If one is found, wait for it to finish before continuing.
            #    This prevents race conditions and ensures proper sequencing.
            #    Note: This should rarely happen since this gear instance
            #    should be the only one triggering pipelines, but it's a safeguard.
            JobPoll.wait_for_pipeline(self.__proxy, job_search)

            log.info(
                "Start processing pipeline: `%s` module queue: `%s`",
                pipeline.name,
                module,
            )

            # Process all files in this module's subqueue
            while len(subqueue) > 0:
                # b. Pull the next file from subqueue and remove queue tags
                file = subqueue.pop(0)
                for tag in pipeline_queue.tags:
                    file.delete_tag(tag)

                # Reload file to get latest state
                # This is critical: without reload, the next gear might add
                # the same queue tags back, causing an infinite loop
                file = file.reload()

                # Set gear inputs of type "matched"
                # This is the actual file being processed from the queue
                if gear_input_info and "matched" in gear_input_info:
                    set_gear_inputs(
                        project=self.__project,
                        gear_name=pipeline.starting_gear.gear_name,
                        locator="matched",
                        gear_inputs_list=gear_input_info["matched"],
                        gear_inputs=gear_inputs,
                        matched_file=file,
                    )

                # c. Trigger the starting gear for this pipeline
                log.info(
                    "Kicking off pipeline `%s` on module %s", pipeline.name, module
                )
                log.info(
                    "Triggering %s for %s", pipeline.starting_gear.gear_name, file.name
                )

                # Get the file's parent container as the gear destination
                destination = self.__proxy.get_container_by_id(
                    file.parent_ref.id  # type: ignore
                )
                trigger_gear(
                    proxy=self.__proxy,
                    gear_name=pipeline.starting_gear.gear_name,
                    log_args=False,
                    inputs=gear_inputs,
                    config=pipeline.starting_gear.configs.model_dump(),
                    destination=destination,
                )

                # d. Wait for the triggered pipeline to complete
                #    This ensures files are processed one at a time
                JobPoll.wait_for_pipeline(self.__proxy, job_search)

                # Capture events if callback provided (finalization pipeline only)
                if event_capture_callback:
                    event_capture_callback(file)

                # e. Send notification email if enabled
                #    Notifies the user who uploaded the file that processing
                #    has completed
                if notify_user and self.__email_client:
                    assert self.__portal_url, "portal URL must be set"
                    send_email(
                        proxy=self.__proxy,
                        email_client=self.__email_client,
                        file=file,
                        project=self.__project.project,
                        portal_url=self.__portal_url,
                    )  # type: ignore

                # f. Repeat until current subqueue is empty

            # Move to next subqueue in round-robin order
            # Repeat steps a-f until all subqueues are empty


class FormSchedulerError(Exception):
    pass
