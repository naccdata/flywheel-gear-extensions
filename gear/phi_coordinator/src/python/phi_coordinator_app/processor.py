"""Per-task resolution for the PHI Coordinator gear.

Defines the Outcome result type and the PHITaskProcessor, which reads a
completed reader task's answer and updates the reviewed file's tags and
the task's processed marker.
"""

import logging
from enum import Enum

from flywheel import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from reader_tasks.reader_task_client import (
    FormResponseModel,
    ReaderTaskClient,
    ReaderTaskModel,
)

log = logging.getLogger(__name__)

# This is a FW value for a Task, not something that needs to be done
_TODO_STATUS = "Todo"


class Outcome(str, Enum):
    """Result of resolving a single completed reader task."""

    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"
    RESET = "reset"
    SKIPPED = "skipped"


class PHITaskProcessor:
    """Resolves a completed PHI reader task into file tags."""

    def __init__(
        self,
        *,
        proxy: FlywheelProxy,
        reader_tasks: ReaderTaskClient,
        answer_key: str,
        ack_key: str,
        found_tag: str,
        confirmed_tag: str,
        not_found_tag: str,
        coordinated_tag: str,
        reset_on_missing_data: bool,
        dry_run: bool,
    ):
        """Initialize the processor with dependencies and configuration.

        Args:
            proxy: Flywheel proxy used to fetch and tag files
            reader_tasks: client for reader-task and form-response calls
            answer_key: response_data key holding the yes/no answer
            ack_key: response_data key for the deletion-acknowledgment
                checkbox that must be checked before a 'yes' is confirmed;
                empty disables the requirement
            found_tag: tag for PHI awaiting review; removed once resolved
            confirmed_tag: tag added when the reviewer confirms PHI
            not_found_tag: tag added when the reviewer reports no PHI
            coordinated_tag: marker added to a task once processed
            reset_on_missing_data: reset tasks lacking a usable answer to Todo
            dry_run: whether to log intended changes without applying them
        """
        self.__proxy = proxy
        self.__reader_tasks = reader_tasks
        self.__answer_key = answer_key
        self.__ack_key = ack_key
        self.__found_tag = found_tag
        self.__confirmed_tag = confirmed_tag
        self.__not_found_tag = not_found_tag
        self.__coordinated_tag = coordinated_tag
        self.__reset_on_missing_data = reset_on_missing_data
        self.__dry_run = dry_run

    def resolve(self, task: ReaderTaskModel) -> Outcome:
        """Resolves one completed task: tags the file, then marks the task.

        Args:
            task: the completed reader task to resolve
        Returns:
            the Outcome describing what was done
        """
        latest = self.__latest_response(task)
        answer = self.__extract_answer(latest)

        file_id = self.__file_id(task)
        if not file_id:
            log.error("Task %s has no associated file; skipping", task.task_id)
            return Outcome.SKIPPED

        if answer not in ("yes", "no"):
            return self.__reset_or_skip(
                task,
                latest,
                reason=(f"is Complete but has no usable '{self.__answer_key}' answer"),
            )

        confirmed = answer == "yes"
        # Confirming PHI deletes the image downstream, so the reviewer must
        # check the acknowledgment before we apply the confirmed tag.
        if confirmed and self.__ack_key and not self.__acknowledged(latest):
            return self.__reset_or_skip(
                task,
                latest,
                reason=(
                    f"confirms PHI but the '{self.__ack_key}' "
                    "acknowledgment is unchecked"
                ),
            )

        desired = self.__confirmed_tag if confirmed else self.__not_found_tag
        opposite = self.__not_found_tag if confirmed else self.__confirmed_tag

        file = self.__proxy.get_file(file_id)
        self.__apply_file_tags(file, desired=desired, opposite=opposite)
        # Mark the task only after the file tags are updated, so a failed tag
        # write leaves the task unmarked and it is retried on the next run.
        self.__mark_task(task)
        return Outcome.CONFIRMED if confirmed else Outcome.NOT_FOUND

    def __latest_response(self, task: ReaderTaskModel) -> FormResponseModel | None:
        """Returns the task's highest-revision form response, or None."""
        responses = self.__reader_tasks.get_responses(task.id)
        if not responses:
            return None
        return max(responses, key=lambda response: response.revision)

    def __extract_answer(self, response: FormResponseModel | None) -> str | None:
        """Returns the lowercased answer for the configured key, or None."""
        if response is None:
            return None
        value = response.response_data.get(self.__answer_key)
        if isinstance(value, str):
            return value.strip().lower()
        return None

    def __acknowledged(self, response: FormResponseModel | None) -> bool:
        """Returns whether the deletion-acknowledgment checkbox is checked."""
        if response is None:
            return False
        return self.__is_checked(response.response_data.get(self.__ack_key))

    @staticmethod
    def __is_checked(value: object) -> bool:
        """Interprets a form acknowledgment value as checked (True) or not.

        The reader form's selectboxes widget serializes checked options as
        a list of their values; a plain checkbox serializes as a boolean.
        """
        if isinstance(value, list):
            return any(bool(item) for item in value)
        if isinstance(value, bool):
            return value
        return False

    @staticmethod
    def __file_id(task: ReaderTaskModel) -> str | None:
        """Returns the id of the file the task reviewed, or None."""
        if task.parent and task.parent.type == "file" and task.parent.id:
            return task.parent.id
        if task.parents and task.parents.file:
            return task.parents.file
        return None

    def __reset_or_skip(
        self,
        task: ReaderTaskModel,
        response: FormResponseModel | None,
        *,
        reason: str,
    ) -> Outcome:
        """Resets the task to Todo and clears its response, or skips it.

        Used when a completed task cannot be applied as submitted: it has no
        usable answer, or it confirms PHI without the required acknowledgment.

        Args:
            task: the completed task that cannot be applied
            response: the task's latest response, cleared when resetting
            reason: short phrase describing why, included in the log message
        Returns:
            SKIPPED when resets are disabled, otherwise RESET
        """
        if not self.__reset_on_missing_data:
            log.warning("Task %s %s; skipping", task.task_id, reason)
            return Outcome.SKIPPED

        if self.__dry_run:
            log.info(
                "Dry run: would reset task %s to Todo and clear its response (%s)",
                task.task_id,
                reason,
            )
            return Outcome.RESET

        log.info(
            "Task %s %s; resetting to Todo and clearing response",
            task.task_id,
            reason,
        )
        self.__reader_tasks.set_task_status(task.id, _TODO_STATUS)
        if response is not None:
            self.__reader_tasks.clear_response(response.id)
        return Outcome.RESET

    def __apply_file_tags(
        self, file: FileEntry, *, desired: str, opposite: str
    ) -> None:
        """Adds the resolution tag; removes PHI-Found and opposite tag."""
        tags = file.tags or []
        # Ordered: add the resolution tag, drop PHI-Found, drop the opposite tag.
        actions: list[tuple[str, str]] = []
        if desired not in tags:
            actions.append(("add", desired))
        if self.__found_tag in tags:
            actions.append(("delete", self.__found_tag))
        if opposite in tags:
            actions.append(("delete", opposite))

        if not actions:
            log.info("File %s already resolved with '%s'", file.name, desired)
            return

        if self.__dry_run:
            for action, tag in actions:
                log.info(
                    "Dry run: would %s tag '%s' on file %s", action, tag, file.name
                )
            return

        for action, tag in actions:
            if action == "add":
                file.add_tag(tag)
                log.info("Added tag '%s' to file %s", tag, file.name)
            else:
                file.delete_tag(tag)
                log.info("Removed tag '%s' from file %s", tag, file.name)
        file.reload()

    def __mark_task(self, task: ReaderTaskModel) -> None:
        """Tags the task as coordinated so later runs exclude it."""
        if self.__dry_run:
            log.info(
                "Dry run: would mark task %s with '%s'",
                task.task_id,
                self.__coordinated_tag,
            )
            return
        self.__reader_tasks.add_task_tag(task, self.__coordinated_tag)
        log.info("Marked task %s with '%s'", task.task_id, self.__coordinated_tag)
