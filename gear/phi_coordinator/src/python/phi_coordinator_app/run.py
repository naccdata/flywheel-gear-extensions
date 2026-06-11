"""Entry point for the PHI Coordinator gear.

Builds the gear execution visitor from the gear context and config, and
defines the main function the container runs.
"""

import logging

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore

from phi_coordinator_app.main import run
from phi_coordinator_app.reader_tasks import ReaderTaskClient

log = logging.getLogger(__name__)


class PHICoordinatorVisitor(GearExecutionEnvironment):
    """Visitor for the PHI Coordinator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        *,
        phi_protocol_label: str,
        answer_key: str,
        found_tag: str,
        confirmed_tag: str,
        not_found_tag: str,
        coordinated_tag: str,
        reset_on_missing_data: bool,
    ):
        """Initialize the visitor with the gear's configuration.

        Args:
            client: Flywheel SDK client wrapper
            phi_protocol_label: label of PHI reader-task protocols to process
            answer_key: response_data key holding the yes/no answer
            found_tag: tag for PHI awaiting review; removed once resolved
            confirmed_tag: tag added when the reviewer confirms PHI
            not_found_tag: tag added when the reviewer reports no PHI
            coordinated_tag: marker added to a task once processed
            reset_on_missing_data: reset tasks lacking a usable answer to Todo
        """
        super().__init__(client=client)
        self.__phi_protocol_label = phi_protocol_label
        self.__answer_key = answer_key
        self.__found_tag = found_tag
        self.__confirmed_tag = confirmed_tag
        self.__not_found_tag = not_found_tag
        self.__coordinated_tag = coordinated_tag
        self.__reset_on_missing_data = reset_on_missing_data

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: ParameterStore | None = None,
    ) -> "PHICoordinatorVisitor":
        """Creates a PHI Coordinator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store.
        Returns:
            the execution environment
        Raises:
            GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)
        opts = context.config.opts

        return PHICoordinatorVisitor(
            client=client,
            phi_protocol_label=opts.get(
                "phi_protocol_label", "default_image_pii_detector_protocol"
            ),
            answer_key=opts.get("answer_key", "phi_radio"),
            found_tag=opts.get("found_tag", "PHI-Found"),
            confirmed_tag=opts.get("confirmed_tag", "PHI-Confirmed"),
            not_found_tag=opts.get("not_found_tag", "PHI-Not-Found"),
            coordinated_tag=opts.get("coordinated_tag", "phi-coordinator"),
            reset_on_missing_data=opts.get("reset_on_missing_data", True),
        )

    def run(self, context: GearContext) -> None:
        """Runs the PHI Coordinator app."""
        reader_tasks = ReaderTaskClient(
            api_client=self.client.client.api_client  # type: ignore
        )

        success = run(
            proxy=self.proxy,
            reader_tasks=reader_tasks,
            phi_protocol_label=self.__phi_protocol_label,
            answer_key=self.__answer_key,
            found_tag=self.__found_tag,
            confirmed_tag=self.__confirmed_tag,
            not_found_tag=self.__not_found_tag,
            coordinated_tag=self.__coordinated_tag,
            reset_on_missing_data=self.__reset_on_missing_data,
            dry_run=self.proxy.dry_run,
        )

        if not success:
            raise GearExecutionError(
                "PHI Coordinator completed with errors; see logs for details"
            )


def main():
    """Main method for PHI Coordinator."""

    GearEngine().run(gear_type=PHICoordinatorVisitor)


if __name__ == "__main__":
    main()
