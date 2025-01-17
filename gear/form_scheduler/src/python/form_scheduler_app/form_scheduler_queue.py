"""Defines the Form Scheduler Queue."""
import re
from typing import Dict, List, Optional, Tuple

from flywheel.models.file_output import FileOutput  # type: ignore
from flywheel.models.project_output import ProjectOutput  # type: ignore
from flywheel_adaptor.flywheel_proxy import FlywheelProxy

MODULE_PATTERN = re.compile(r"^.+-([a-zA-Z]+)(\..+)$")


class FormSchedulerQueue:
    """Class to define a queue for each accepted module, with prioritization
    allowed."""

    def __init__(self, proxy: FlywheelProxy, module_order: List[str],
                 queue_tags: List[str]) -> None:
        """Initializer.

        Args:
            proxy: the proxy for the Flywheel instance
            module_order: The modules and the order to process them in
            queue_tags: The queue tags to filter project files for
                to determine which need to be queued
        """
        self.__proxy = proxy
        self.__module_order = module_order
        self.__index = -1
        self.queue_tags = set(queue_tags)  # make set for comparison later
        self.__queue: Dict[str, List[FileOutput]] = {
            k: []
            for k in self.__module_order
        }

    def add_files(self,
                  project: ProjectOutput,
                  file_extensions: Optional[List[str]] = None) -> int:
        """Add the files (filtered by queue tags) to queue.

        Args:
            project: Project to pull queue files from
            file_extensions: List of file extensions to grab
        Returns:
            The number of files added to the queue
        """
        if not file_extensions:
            file_extensions = ['.csv']

        files = [
            x for x in project.files if self.queue_tags.issubset(set(x.tags))
        ]
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
            if ext not in file_extensions:
                continue

            # add to queue
            self.__queue[module].append(file)
            num_files += 1

        # sort each queue by last modified date
        for subqueue in self.__queue.values():
            subqueue.sort(key=lambda file: file.modified)

        return num_files

    def next_queue(self) -> Tuple[str, List[FileOutput]]:
        """Returns the next queue in the round robin.

        Returns:
            Tuple with the module name and its corresponding
            queue to be processed.
        """
        self.__index = (self.__index + 1) % len(self.__module_order)
        module = self.__module_order[self.__index]
        return module, self.__queue[module]

    def empty(self) -> bool:
        """Returns whether or not the queue is empty.

        Returns:
            True if the queue is empty, False otherwise.
        """
        return all(not x for x in self.__queue.values())
