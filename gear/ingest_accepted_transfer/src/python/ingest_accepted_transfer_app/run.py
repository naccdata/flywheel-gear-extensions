"""Entry script for Ingest to Accepted Transfer."""

import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
)
from inputs.parameter_store import ParameterStore
from keys.keys import DefaultValues

from ingest_accepted_transfer_app.main import run

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

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)


def main():
    """Main method for Ingest Accepted Transfer."""

    GearEngine().run(gear_type=IngestAcceptedTransferVisitor)


if __name__ == "__main__":
    main()
