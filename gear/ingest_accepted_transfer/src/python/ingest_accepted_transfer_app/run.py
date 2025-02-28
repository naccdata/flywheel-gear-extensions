"""Entry script for Ingest to Accepted Transfer."""

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
)
from ingest_accepted_transfer_app.main import run
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues

log = logging.getLogger(__name__)


class IngestAcceptedTransferVisitor(GearExecutionEnvironment):
    """Visitor for the Ingest Accepted Transfer gear."""

    def __init__(self, *, client: ClientWrapper, admin_id: str,
                 ingest_project: str, accepted_project: str,
                 time_interval: int, batch_size: int):
        """
        Args:
            client: Flywheel SDK client wrapper
            admin_id: admin group id
            ingest_project: ingest project label
            accepted_project: accepted project label
            time_interval: time interval in days between the runs (input -1 to ignore)
            batch_size: number of acquisition files to queue for one batch
        """
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__ingest_project = ingest_project
        self.__accepted_project = accepted_project
        self.__time_interval = time_interval
        self.__batch_size = batch_size

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'IngestAcceptedTransferVisitor':
        """Creates a Ingest Accepted Transfer execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = ContextClient.create(context=context)

        return IngestAcceptedTransferVisitor(
            client=client,
            admin_id=context.config.get("admin_group",
                                        DefaultValues.NACC_GROUP_ID),
            ingest_project=context.config.get("ingest_project",
                                              DefaultValues.LEGACY_PRJ_LABEL),
            accepted_project=context.config.get(
                "accepted_project", DefaultValues.ACCEPTED_PRJ_LBL),
            time_interval=context.config.get("time_interval", 7),
            batch_size=context.config.get("batch_size", 10000))

    def __get_center_ids(self) -> Optional[List[str]]:
        """Get the list of Center IDs from metadata project.

        Returns:
            Optional[List[str]]: list of Center IDs if found
        """
        nacc_group = self.admin_group(admin_id=self.__admin_id)
        centers: Dict[int, CenterInfo] = nacc_group.get_center_map().centers
        if not centers:
            return None

        exclude_groups = ['sample-center', 'allftd']
        exclude_suffix = ('dlb', 'dvcid', 'leads', 'ftld')

        center_ids = [
            center.group for center in centers.values()
            if center.group not in exclude_groups
            and not center.group.endswith(exclude_suffix)
        ]
        return center_ids

    def run(self, context: GearToolkitContext) -> None:
        """Invoke the ingest to accepted copy app.

        Args:
            context: the gear execution context

        Raises:
            GearExecutionError if errors occur while copying data
        """

        centers = self.__get_center_ids()
        if not centers:
            raise GearExecutionError(
                'Center information not found in '
                f'{self.__admin_id}/{DefaultValues.METADATA_PRJ_LBL}')

        run(proxy=self.proxy,
            centers=centers,
            ingest_project_lbl=self.__ingest_project,
            accepted_project_lbl=self.__accepted_project,
            time_interval=self.__time_interval,
            batch_size=self.__batch_size,
            dry_run=context.config.get("dry_run", False))


def main():
    """Main method for Ingest Accepted Transfer."""

    GearEngine().run(gear_type=IngestAcceptedTransferVisitor)


if __name__ == "__main__":
    main()
