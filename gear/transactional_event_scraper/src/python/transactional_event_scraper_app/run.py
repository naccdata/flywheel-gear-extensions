"""Entry script for Transactional Event Scraper."""

import logging
from typing import Optional

from event_capture.event_capture import VisitEventCapture
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore
from s3.s3_bucket import S3BucketInterface

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
        project: ProjectAdaptor,
        event_capture: Optional[VisitEventCapture] = None,
    ):
        """Initialize the visitor.

        Args:
            client: The client wrapper
            config: The gear configuration
            project: The project adaptor
            event_capture: Optional event capture for storing events (None for dry-run)
        """
        super().__init__(client=client)
        self.__config = config
        self.__project = project
        self.__event_capture = event_capture

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "TransactionalEventScraperVisitor":
        """Creates a Transactional Event Scraper execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store

        Returns:
            the execution environment

        Raises:
            GearExecutionError if any expected inputs are missing or configuration
            is invalid
        """
        assert parameter_store, "Parameter store expected"

        # Parse gear configuration
        config = parse_gear_config(context)

        # Create client with GearBot credentials
        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        # Get destination project
        dest_container = context.config.get_destination_container()
        if not dest_container:
            raise GearExecutionError("No destination container found")

        if dest_container.container_type != "project":  # type: ignore[union-attr]
            raise GearExecutionError(
                f"Unsupported container type {dest_container.container_type}, "  # type: ignore[union-attr]
                f"this gear must be executed at project level"
            )

        project_id = dest_container.id  # type: ignore[union-attr]

        # Get project from Flywheel
        proxy = client.get_proxy()
        fw_project = proxy.get_project_by_id(project_id)
        if not fw_project:
            raise GearExecutionError(f"Cannot find project with ID {project_id}")

        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        # Initialize visit event capture if not in dry-run mode
        event_capture = None
        if not config.dry_run:
            s3_bucket = S3BucketInterface.create_from_environment(config.event_bucket)
            event_capture = VisitEventCapture(
                s3_bucket=s3_bucket, environment=config.event_environment
            )
            log.info(
                f"Visit event capture initialized for environment "
                f"'{config.event_environment}' with bucket "
                f"'{config.event_bucket}'"
            )
        else:
            log.info("Dry-run mode enabled: events will not be captured to S3")

        return TransactionalEventScraperVisitor(
            client=client,
            config=config,
            project=project,
            event_capture=event_capture,
        )

    def run(self, context: GearContext) -> None:
        """Run the transactional event scraper.

        Args:
            context: The gear context

        Raises:
            GearExecutionError if the scraping process fails
        """
        log.info("Running Transactional Event Scraper")
        log.info(
            f"Configuration: dry_run={self.__config.dry_run}, "
            f"event_bucket={self.__config.event_bucket}, "
            f"event_environment={self.__config.event_environment}"
        )

        if self.__config.start_date or self.__config.end_date:
            log.info(
                f"Date filtering: start_date={self.__config.start_date}, "
                f"end_date={self.__config.end_date}"
            )

        # Get date range filter
        date_filter = self.__config.get_date_range()

        # Create EventScraper
        from transactional_event_scraper_app.event_scraper import EventScraper

        scraper = EventScraper(
            project=self.__project,
            event_capture=self.__event_capture,
            dry_run=self.__config.dry_run,
            date_filter=date_filter,
        )

        # Run the scraper
        run(scraper=scraper)
        log.info("Scraping completed successfully")


def main():
    """Main method for Transactional Event Scraper."""
    GearEngine.create_with_parameter_store().run(
        gear_type=TransactionalEventScraperVisitor
    )


if __name__ == "__main__":
    main()
