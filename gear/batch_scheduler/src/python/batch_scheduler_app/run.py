"""Entry script for batch scheduler."""

import logging
from typing import Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from gear_execution.gear_trigger import BatchRunInfo
from inputs.parameter_store import ParameterStore

from batch_scheduler_app.main import run

log = logging.getLogger(__name__)


class BatchSchedulerVisitor(GearExecutionEnvironment):
    """Visitor for the batch-scheduler gear."""

    def __init__(
        self,
        *,
        client: ClientWrapper,
        config_input: InputFileWrapper,
        time_interval: int = 7,
        retry_jobs: bool = True,
    ):
        """
        Args:
            client: Flywheel SDK client wrapper
            config_input: batch run configs file wrapper
            time_interval: time interval in days between the runs (input -1 to ignore)
            retry_jobs: whether or not to retry jobs
        """
        super().__init__(client=client)
        self.__config_input = config_input
        self.__time_interval = time_interval
        self.__retry_jobs = retry_jobs

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "BatchSchedulerVisitor":
        """Creates a batch scheduler execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        batch_configs_input = InputFileWrapper.create(
            input_name="batch_configs_file", context=context
        )
        assert batch_configs_input, "missing expected input, batch_configs_file"

        return BatchSchedulerVisitor(
            client=client,
            config_input=batch_configs_input,
            time_interval=context.config.get("time_interval", 7),
            retry_jobs=context.config.get("retry_jobs", True),
        )

    def run(self, context: GearToolkitContext) -> None:
        """Invoke the batch scheduler app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if errors occur while running batch schedule
        """

        centers = self.get_center_ids(context)
        if not centers:
            log.warning("Did not find any centers matching with specified configs")
            return

        batch_configs = BatchRunInfo.load_from_file(self.__config_input.filepath)
        if not batch_configs:
            raise GearExecutionError(
                "Error in parsing batch run configs file "
                f"{self.__config_input.filename}"
            )

        options = context.config.opts
        sender_email = options.get("sender_email", "nacchelp@uw.edu")
        target_emails = options.get("target_emails", "nacc_dev@uw.edu")
        target_emails = [x.strip() for x in target_emails.split(",")]

        run(
            proxy=self.proxy,
            centers=centers,
            time_interval=self.__time_interval,
            batch_configs=batch_configs,
            sender_email=sender_email,
            target_emails=target_emails,
            retry_jobs=self.__retry_jobs,
            dry_run=options.get("dry_run", False),
        )


def main():
    """Main method for batch scheduler."""

    GearEngine().run(gear_type=BatchSchedulerVisitor)


if __name__ == "__main__":
    main()
