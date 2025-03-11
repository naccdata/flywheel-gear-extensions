"""Entry script for batch scheduler."""

import logging
from typing import Dict, List, Optional

from centers.center_info import CenterInfo
from flywheel_gear_toolkit import GearToolkitContext
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
from keys.keys import DefaultValues
from utils.utils import parse_string_to_list

from batch_scheduler_app.main import run

log = logging.getLogger(__name__)


class BatchSchedulerVisitor(GearExecutionEnvironment):
    """Visitor for the batch-scheduler gear."""

    def __init__(self, *, client: ClientWrapper, admin_id: str,
                 config_input: InputFileWrapper, exclude_centers: List[str],
                 exclude_studies: List[str], time_interval: int):
        """
        Args:
            client: Flywheel SDK client wrapper
            admin_id: admin group id
            config_input: batch run configs file wrapper
            exclude_centers: list of centers to exclude from batch run
            exclude_studies: list of study suffixes to exclude from batch run
            time_interval: time interval in days between the runs (input -1 to ignore)
        """
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__config_input = config_input
        self.__exclude_centers = exclude_centers
        self.__exclude_studies = exclude_studies
        self.__time_interval = time_interval

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'BatchSchedulerVisitor':
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
            input_name='batch_configs_file', context=context)
        assert batch_configs_input, "missing expected input, batch_configs_file"

        exclude_centers = context.config.get("exclude_centers", None)
        exclude_centers_list = parse_string_to_list(
            exclude_centers) if exclude_centers else []

        exclude_studies = context.config.get("exclude_studies", None)
        exclude_studies_list = parse_string_to_list(
            exclude_studies) if exclude_studies else []

        log.info('Skipping centers %s', exclude_centers_list)
        log.info('Skipping studies %s', exclude_studies_list)

        return BatchSchedulerVisitor(
            client=client,
            admin_id=context.config.get("admin_group",
                                        DefaultValues.NACC_GROUP_ID),
            config_input=batch_configs_input,
            exclude_centers=exclude_centers_list,
            exclude_studies=exclude_studies_list,
            time_interval=context.config.get("time_interval", 7))

    def __get_center_ids(self) -> Optional[List[str]]:
        """Get the list of Center IDs from metadata project.

        Returns:
            Optional[List[str]]: list of Center IDs if found
        """
        nacc_group = self.admin_group(admin_id=self.__admin_id)
        centers: Dict[int, CenterInfo] = nacc_group.get_center_map().centers
        if not centers:
            raise GearExecutionError(
                'Center information not found in '
                f'{self.__admin_id}/{DefaultValues.METADATA_PRJ_LBL}')

        center_ids = [
            center.group for center in centers.values()
            if center.group not in self.__exclude_centers
            and not center.group.endswith(tuple(self.__exclude_studies))
        ]

        return center_ids

    def run(self, context: GearToolkitContext) -> None:
        """Invoke the batch scheduler app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if errors occur while running batch schedule
        """

        centers = self.__get_center_ids()
        if not centers:
            log.warning(
                "Did not find any centers matching with specified configs")
            return

        batch_configs = BatchRunInfo.load_from_file(
            self.__config_input.filepath)
        if not batch_configs:
            raise GearExecutionError('Error in parsing batch run configs file '
                                     f'{self.__config_input.filename}')

        sender_email = context.config.get('sender_email',
                                          'no-reply@naccdata.org')
        target_emails = context.config.get('target_emails', 'nacc_dev@uw.edu')
        target_emails = [x.strip() for x in target_emails.split(',')]

        run(proxy=self.proxy,
            centers=centers,
            time_interval=self.__time_interval,
            batch_configs=batch_configs,
            sender_email=sender_email,
            target_emails=target_emails,
            dry_run=context.config.get("dry_run", False))


def main():
    """Main method for batch scheduler."""

    GearEngine().run(gear_type=BatchSchedulerVisitor)


if __name__ == "__main__":
    main()
