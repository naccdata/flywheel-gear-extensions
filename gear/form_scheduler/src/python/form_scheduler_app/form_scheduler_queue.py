"""Defines the Form Scheduler Queue."""

import json
import logging
import re
from json.decoder import JSONDecodeError
from typing import Dict, List, Optional, Tuple

from configs.ingest_configs import (
    Pipeline,
    PipelineConfigs,
    PipelineType,
)
from data.dataview import ColumnModel, make_builder
from event_logging.event_logging import VisitEventLogger
from event_logging.visit_event_accumulator import VisitEventAccumulator
from flywheel import Project
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import (
    set_gear_inputs,
    trigger_gear,
)
from inputs.parameter_store import URLParameter
from jobs.job_poll import JobPoll
from notifications.email import EmailClient
from pydantic import BaseModel, ConfigDict

from form_scheduler_app.email_user import send_email

MODULE_PATTERN = re.compile(r"^.*-([a-zA-Z]+)(\..+)$")

log = logging.getLogger(__name__)


class PipelineQueue(BaseModel):
    """Class to represent a file queue for a given pipeline, with subqueues
    defined for each module accepted for the pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: int = -1
    name: PipelineType
    tags: List[str]
    modules: List[str]
    subqueues: Dict[str, List[FileEntry]]

    @classmethod
    def create_from_pipeline(cls, pipeline: Pipeline) -> "PipelineQueue":
        """Initialize the pipeline queue from pipeline configs.

        Args:
            pipeline: pipeline configurations

        Returns:
            PipelineQueue: file queue for the pipeline
        """
        return PipelineQueue(
            name=pipeline.name,
            tags=pipeline.tags,
            modules=pipeline.modules,
            subqueues={k: [] for k in pipeline.modules},
        )

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
        """Sort each queue by ascending order of file modified date."""
        for subqueue in self.subqueues.values():
            subqueue.sort(key=lambda file: file.modified)

    def next_queue(self) -> Tuple[str, List[FileEntry]]:
        """Returns the next module queue for the pipeline.

        Returns:
            Tuple with the module name and its corresponding
            queue to be processed.
        """
        self.index = (self.index + 1) % len(self.modules)
        module = self.modules[self.index]
        return module, self.subqueues[module]

    def empty(self) -> bool:
        """Returns whether or not all the subqueues are empty.

        Returns:
            True if all subqueues are empty, False otherwise.
        """
        return all(not x for x in self.subqueues.values())


class FormSchedulerQueue:
    """Class to handle scheduling of different form pipelines defined in the
    pipeline configs file."""

    def __init__(
        self,
        proxy: FlywheelProxy,
        project: Project,
        pipeline_configs: PipelineConfigs,
        event_logger: VisitEventLogger,
        event_accumulator: VisitEventAccumulator,
        email_client: Optional[EmailClient] = None,
        portal_url: Optional[URLParameter] = None,
    ) -> None:
        """Initializer.

        Args:
            proxy: the proxy for the Flywheel instance
            project: Flywheel project container
            pipeline_configs: form pipeline configurations
            event_logger: VisitEventLogger for logging visit events
            event_accumulator: VisitEventAccumulator for tracking visit events
            email_client: EmailClient to send emails from
            portal_url: The portal URL
        """
        self.__proxy = proxy
        self.__project = project
        self.__pipeline_configs = pipeline_configs
        self.__email_client = email_client
        self.__portal_url = portal_url
        self.__pipeline_queues: Dict[str, PipelineQueue] = {}
        self.__event_logger: VisitEventLogger = event_logger
        self.__event_accumulator = event_accumulator

    def queue_files_for_pipeline(self, *, project: Project, pipeline: Pipeline) -> int:
        """Queue the matching files for the given pipeline.

        Args:
            project: Flywheel project container
            pipeline: Pipeline configurations

        Returns:
            int: Number of files added to the pipeline queue
        """

        function_name = f"_add_{pipeline.name}_pipeline_files"
        pipeline_function = getattr(self, function_name, None)
        if pipeline_function and callable(pipeline_function):
            num_files = pipeline_function(project=project, pipeline=pipeline)
            log.info(
                f"Number of files queued for pipeline `{pipeline.name}`: {num_files}"
            )
            return num_files  # type: ignore
        else:
            raise GearExecutionError(
                f"{function_name} not defined in the Form Scheduler"
            )

    def _add_submission_pipeline_files(
        self, *, project: Project, pipeline: Pipeline
    ) -> int:
        """Add the files (filtered by queue tags) to submission pipeline queue.

        Args:
            project: Project to pull queue files from
            pipeline: Pipeline configurations

        Returns:
            The number of files added to the submission pipeline queue
        """

        # filter project files with matching tags and extensions
        files: List[FileEntry] = [
            x
            for x in project.files
            if (
                set(pipeline.tags).issubset(set(x.tags))
                and x.name.lower().endswith(tuple(pipeline.extensions))
            )
        ]

        if len(files) == 0:
            log.info(
                f"No matching files for pipeline `{pipeline.name}` with "
                f"tags: {pipeline.tags} and extensions: {pipeline.extensions}"
            )
            return 0

        pipeline_queue = PipelineQueue.create_from_pipeline(pipeline=pipeline)

        # grabs files in the format *-<module>.<ext>
        num_files = 0
        for file in files:
            match = re.search(MODULE_PATTERN, file.name.lower())
            # skip over files that do not match regex - form-screening gear should
            # check this so these should just be files that were incorrectly tagged
            # by something else
            if not match:
                log.warning(
                    "File %s is incorrectly tagged with one or more tags %s",
                    file.name,
                    pipeline.tags,
                )
                continue

            module = match.group(1)

            # add the file to the respective module queue
            if not pipeline_queue.add_file_to_subqueue(module=module, file=file):
                continue

            # Record file queued for event tracking
            self.__event_accumulator.record_file_queued(
                file=file, module=module, project=project
            )

            num_files += 1

        # sort the files in each subqueue by ascending order of last modified date
        pipeline_queue.sort_subqueues()
        self.__pipeline_queues[pipeline.name] = pipeline_queue

        return num_files

    def _add_finalization_pipeline_files(
        self, *, project: Project, pipeline: Pipeline
    ) -> int:
        """Add the files (filtered by queue tags) to finalization pipeline
        queue.

        Args:
            project: Project to pull queue files from
            pipeline: Pipeline configurations

        Returns:
            The number of files added to the finalization pipeline queue
        """

        # TODO: Find a way to search multiple tags
        # Checked with FW and multi tag OR search currently doesn't work
        # finalization pipeline currently only has one tag, so no issue for now
        if len(pipeline.tags) > 1:
            raise GearExecutionError(
                f"Cannot support searching for multiple file tags {pipeline.tags}"
            )

        # find the list of visits with matching tags and extensions
        # for the modules accepted for this pipeline
        finalized_visits = self.__find_matching_visits_for_the_pipeline(
            project=project, pipeline=pipeline
        )

        if not finalized_visits:
            log.info(
                "No matching files for pipeline `%s` with tags: %s and extensions: %s",
                pipeline.name,
                pipeline.tags,
                pipeline.extensions,
            )
            return 0

        pipeline_queue = PipelineQueue.create_from_pipeline(pipeline=pipeline)

        num_files = 0
        for visit in finalized_visits:
            visit_file = self.__proxy.get_file(visit["file_id"])
            # add the file to the respective module queue
            if not pipeline_queue.add_file_to_subqueue(
                module=visit["module"], file=visit_file
            ):
                continue

            num_files += 1

        # sort the files in each subqueue by ascending order of last modified date
        pipeline_queue.sort_subqueues()
        self.__pipeline_queues[pipeline.name] = pipeline_queue

        return num_files

    def __find_matching_visits_for_the_pipeline(
        self, *, project: Project, pipeline: Pipeline
    ) -> Optional[List[Dict[str, str]]]:
        """Find the visit files with matching modules, tags and extensions for
        the specified pipeline.

        Args:
            project: Flywheel project container
            pipeline: Pipeline configurations

        Returns:
            List[Dict[str, str]](optional): matching visits if found
        """

        modules = pipeline.modules
        tag = pipeline.tags[0]
        extensions = pipeline.extensions

        filename_pattern = ""
        filename_pattern += "|".join(f"^.*\\{ext}$" for ext in extensions)

        builder = make_builder(
            label=f"Participant visits with tags {tag}",
            description="List of finalized visits for the module",
            columns=[
                ColumnModel(data_key="file.name", label="filename"),
                ColumnModel(data_key="file.file_id", label="file_id"),
                ColumnModel(data_key="acquisition.label", label="module"),
                ColumnModel(data_key="file.tags", label="file_tags"),
            ],
            container="acquisition",
            filter_str=f"acquisition.label=|[{','.join(modules)}],file.tags={tag}",
            missing_data_strategy="drop-row",
        )

        builder.file_filter(value=filename_pattern, regex=True)
        # need to set the container again (should be same as "container" given above)
        # if only file_filter is set, FW reports following error
        # ValueError: Both file_container and file_filter are required to process files
        builder.file_container("acquisition")
        view = builder.build()

        with self.__proxy.read_view_data(view=view, container_id=project.id) as resp:
            try:
                result = json.load(resp)
            except JSONDecodeError as error:
                log.error(
                    "Error in loading dataview %s on container %s: %s",
                    view.label,
                    project.id,
                    error,
                )
                return None

        if not result or "data" not in result:
            return None

        return result["data"]

    def process_pipeline_queues(self):
        """Process the pipeline queues.

        Raises:
            GearExecutionError: if problems occur while processing
        """
        # search string to use for looking up running pipelines
        search_str = JobPoll.generate_search_string(
            project_ids_list=[self.__project.id],
            gears_list=self.__pipeline_configs.gears,
            states_list=["running", "pending"],
        )

        # Pipelines are processed in the order they are listed in the pipeline configs
        for pipeline in self.__pipeline_configs.pipelines:
            # Skip pipelines with no queued files
            if pipeline.name not in self.__pipeline_queues:
                continue

            try:
                self._process_pipeline_queue(
                    pipeline=pipeline,
                    pipeline_queue=self.__pipeline_queues[pipeline.name],
                    job_search=search_str,
                    notify_user=pipeline.notify_user,
                )
            except ValueError as error:
                raise GearExecutionError(
                    f"Failed to process pipeline `{pipeline.name}`: {error}"
                ) from error

    def _process_pipeline_queue(
        self,
        *,
        pipeline: Pipeline,
        pipeline_queue: PipelineQueue,
        job_search: str,
        notify_user: bool,
    ):
        """Process the files in the specified pipeline queue. Trigger the
        starting gear for the pipeline for each file in pipeline queue.

        Args:
            pipeline: pipeline configs
            pipeline_queue: files queued for this pipeline
            job_search: lookup string to find running pipelines
            notify_user: whether to notify the user about completion of pipeline
        """

        # get the starting gear input file configurations
        gear_input_info = pipeline.starting_gear.get_inputs_by_file_locator_type(
            locators=["fixed", "matched", "module"]
        )

        gear_inputs: Dict[str, FileEntry] = {}

        # set gear inputs of file locator type fixed
        # these are the project level files with fixed filename specified in the configs
        if gear_input_info and "fixed" in gear_input_info:
            set_gear_inputs(
                project=self.__project,
                gear_name=pipeline.starting_gear.gear_name,
                locator="fixed",
                gear_inputs_list=gear_input_info["fixed"],
                gear_inputs=gear_inputs,
            )

        while not pipeline_queue.empty():
            # Grab the next module subqueue for this pipeline
            module, subqueue = pipeline_queue.next_queue()
            if not subqueue:
                continue

            # set gear inputs of file locator type module
            # for these inputs, each module has a module specific file at project level
            # need to substitute module in the filename specified in the configs
            if gear_input_info and "module" in gear_input_info:
                set_gear_inputs(
                    project=self.__project,
                    gear_name=pipeline.starting_gear.gear_name,
                    locator="module",
                    gear_inputs_list=gear_input_info["module"],
                    gear_inputs=gear_inputs,
                    module=module,
                )

            # a. Check if any submission pipelines are already running for
            #    this project. If one is found, wait for it to finish before continuing.
            #    This should actually not happen as it would mean that this gear
            #    instance is not the owner/trigger of this submission pipeline,
            #    but left in as a safeguard
            JobPoll.wait_for_pipeline(self.__proxy, job_search)

            log.info(
                "Start processing pipeline: `%s` module queue: `%s`",
                pipeline.name,
                module,
            )

            while len(subqueue) > 0:
                # b. Pull the next file from subqueue and clear the queue tags
                file = subqueue.pop(0)
                for tag in pipeline_queue.tags:
                    file.delete_tag(tag)

                # need to reload else the next gear may add the same queue tags back in
                # causing an infinite loop
                file = file.reload()

                # set gear inputs of file locator type matched
                # for these inputs, use the file entry pulled from the queue
                if gear_input_info and "matched" in gear_input_info:
                    set_gear_inputs(
                        project=self.__project,
                        gear_name=pipeline.starting_gear.gear_name,
                        locator="matched",
                        gear_inputs_list=gear_input_info["matched"],
                        gear_inputs=gear_inputs,
                        matched_file=file,
                    )

                # c. Trigger the first gear for the respective pipeline.
                log.info(f"Kicking off pipeline `{pipeline.name}` on module {module}")
                log.info(
                    f"Triggering {pipeline.starting_gear.gear_name} for {file.name}"
                )

                destination = self.__proxy.get_container_by_id(file.parent_ref.id)  # type: ignore
                trigger_gear(
                    proxy=self.__proxy,
                    gear_name=pipeline.starting_gear.gear_name,
                    log_args=False,
                    inputs=gear_inputs,
                    config=pipeline.starting_gear.configs.model_dump(),
                    destination=destination,
                )

                # d. wait for the above triggered pipeline to finish
                JobPoll.wait_for_pipeline(self.__proxy, job_search)

                # Determine if pipeline succeeded by checking QC metadata
                pipeline_succeeded = self.__check_pipeline_success(file, module)

                # Finalize and log events
                try:
                    self.__event_accumulator.finalize_and_log_events(
                        file=file,
                        module=module,
                        pipeline_succeeded=pipeline_succeeded,
                    )
                except Exception as error:
                    log.warning(
                        f"Failed to log events for {file.name}: {error}",
                        exc_info=True,
                    )

                # e. if notifications enabled,
                #    email to user who uploaded the file that pipeline has completed
                if notify_user and self.__email_client and pipeline_succeeded:
                    assert self.__portal_url, "portal URL must be set"
                    send_email(
                        proxy=self.__proxy,
                        email_client=self.__email_client,
                        file=file,
                        project=self.__project,
                        portal_url=self.__portal_url,
                    )  # type: ignore

                # f. repeat until current subqueue is empty

            # Move to next subqueue, repeat a - f until all subqueues are empty

    def __check_pipeline_success(self, file: FileEntry, module: str) -> bool:
        """Check if pipeline completed successfully using QC metadata.

        Checks for JSON file at ACQUISITION level and validates that ALL
        pipeline gears have status="PASS" in QC metadata.

        Args:
            file: The original CSV file
            module: Module name

        Returns:
            True if JSON exists and all gears passed QC, False otherwise
        """
        try:
            from nacc_common.error_models import FileQCModel
            from pydantic import ValidationError

            acquisition_id = file.parent_ref.id
            acquisition = self.__proxy.get_container_by_id(acquisition_id)

            # Look for JSON file at ACQUISITION level
            json_files = [f for f in acquisition.files if f.name.endswith(".json")]

            if not json_files:
                log.info(
                    f"No JSON file found for {file.name} - "
                    f"pipeline failed at identifier-lookup or form-transformer"
                )
                return False

            # If multiple JSON files, try to match by module
            json_file = None
            if len(json_files) > 1:
                module_lower = module.lower()
                matching = [f for f in json_files if module_lower in f.name.lower()]
                if not matching:
                    log.warning(
                        f"No JSON file matching module {module} for {file.name}"
                    )
                    return False
                json_file = matching[0]
            else:
                json_file = json_files[0]

            # Reload to get latest metadata
            json_file = json_file.reload()

            # Parse QC metadata using nacc_common models
            if not json_file.info or "qc" not in json_file.info:
                log.warning(f"No QC metadata in {json_file.name}")
                return False

            try:
                qc_model = FileQCModel.model_validate(json_file.info)
            except ValidationError as error:
                log.warning(f"Failed to parse QC metadata: {error}")
                return False

            # Check status of all pipeline gears
            # ALL gears must have status="PASS" for success
            pipeline_gears = [
                "form-screening",
                "identifier-lookup",
                "form-transformer",
                "form-qc-checker",
            ]

            for gear_name in pipeline_gears:
                status = qc_model.get_status(gear_name)

                if status is None:
                    # Gear hasn't run yet - pipeline incomplete
                    log.info(
                        f"Gear {gear_name} has not run for {file.name} - "
                        f"pipeline incomplete"
                    )
                    return False

                if status != "PASS":
                    log.info(
                        f"Gear {gear_name} has status '{status}' for {file.name} - "
                        f"pipeline did not pass QC"
                    )
                    return False

            # All gears passed - this is the ONLY case for success
            log.info(f"All gears passed QC for {file.name}")
            return True

        except Exception as error:
            log.warning(f"Error checking pipeline success: {error}")
            return False
