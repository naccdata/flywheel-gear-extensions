"""Entry script for Transactional Event Scraper."""

import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore

from transactional_event_scraper_app.config import (
    TransactionalEventScraperConfig,
    parse_gear_config,
)
from transactional_event_scraper_app.main import run

log = logging.getLogger(__name__)


class TransactionalEventScraperVisitor(GearExecutionEnvironment):
    """Visitor for the Transactional Event Scraper gear."""

    def __init__(
        self,
        client: ClientWrapper,
        config: TransactionalEventScraperConfig,
        dry_run: bool = False,
    ):
        """Initialize the visitor.

        Args:
            client: The client wrapper
            config: The gear configuration
            dry_run: Whether to perform a dry run
        """
        super().__init__(client=client)
        self.__config = config
        self.__dry_run = dry_run

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "TransactionalEventScraperVisitor":
        """Creates a Transactional Event Scraper execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store

        Returns:
            the execution environment

        Raises:
            GearExecutionError if any expected inputs are missing
        """
        try:
            config = parse_gear_config(context)
            client = ContextClient.create(context=context)

            return TransactionalEventScraperVisitor(
                client=client, config=config, dry_run=config.dry_run
            )
        except Exception as e:
            error_msg = f"Failed to create TransactionalEventScraperVisitor: {e}"
            log.error(error_msg)
            raise GearExecutionError(error_msg) from e

    def run(self, context: GearToolkitContext) -> None:
        """Run the transactional event scraper.

        Args:
            context: The gear context
        """
        try:
            log.info("Running Transactional Event Scraper")
            results = run(
                proxy=self.proxy, config=self.__config, dry_run=self.__dry_run
            )
            log.info(f"Scraping completed successfully: {results}")
        except Exception as e:
            error_msg = f"Transactional Event Scraper execution failed: {e}"
            log.error(error_msg)
            raise GearExecutionError(error_msg) from e


def main():
    """Main method for Transactional Event Scraper."""
    GearEngine().run(gear_type=TransactionalEventScraperVisitor)


if __name__ == "__main__":
    main()
