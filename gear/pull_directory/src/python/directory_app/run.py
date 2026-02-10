"""Script to pull directory information and convert to file expected by the
user management gear."""

import logging
from typing import Dict, List, Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterError, ParameterStore
from notifications.email import EmailClient, create_ses_client
from redcap_api.redcap_connection import REDCapConnectionError, REDCapReportConnection
from users.csv_export import export_errors_to_csv
from users.event_models import UserEventCollector
from yaml.representer import RepresenterError

from directory_app.main import run

log = logging.getLogger(__name__)


class DirectoryPullVisitor(GearExecutionEnvironment):
    """Defines the directory pull gear."""

    def __init__(
        self,
        client: ClientWrapper,
        user_filename: str,
        user_report: List[Dict[str, str]],
        collector: Optional[UserEventCollector] = None,
        email_source: Optional[str] = None,
        support_emails: Optional[List[str]] = None,
    ):
        super().__init__(client=client)
        self.__user_filename = user_filename
        self.__user_report = user_report
        self.__collector = collector if collector is not None else UserEventCollector()
        self.__email_source = email_source
        self.__support_emails = support_emails or []

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore]
    ) -> "DirectoryPullVisitor":
        """Creates directory pull execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Returns:
          the DirectoryPullVisitor
        Raises:
          GearExecutionError if the config or parameter path are missing values
        """
        assert parameter_store, "Parameter store expected"

        client = ContextClient.create(context)
        param_path = context.config.opts.get("parameter_path")
        if not param_path:
            raise GearExecutionError("No parameter path")

        try:
            report_parameters = parameter_store.get_redcap_report_parameters(
                param_path=param_path
            )
        except ParameterError as error:
            raise GearExecutionError(f"Parameter error: {error}") from error

        try:
            directory_proxy = REDCapReportConnection.create_from(report_parameters)
            user_report = directory_proxy.get_report_records()
        except REDCapConnectionError as error:
            raise GearExecutionError(
                f"Failed to pull users from directory: {error.message}"
            ) from error

        user_filename = context.config.opts.get("user_file")
        if not user_filename:
            raise GearExecutionError("No user file name provided")

        # Create error collector as core functionality
        collector = UserEventCollector()

        # Get notification configuration (required)
        notifications_path = context.config.opts.get(
            "notifications_path", "/prod/notifications"
        )
        if not notifications_path:
            raise GearExecutionError("No notifications parameter path")

        try:
            notification_params = parameter_store.get_notification_parameters(
                notifications_path
            )
        except ParameterError as error:
            raise GearExecutionError(
                f"Failed to load notification configuration: {error}"
            ) from error

        return DirectoryPullVisitor(
            client=client,
            user_filename=user_filename,
            user_report=user_report,
            collector=collector,
            email_source=notification_params["sender"],
            support_emails=cls._parse_support_emails(
                notification_params["support_emails"]
            ),
        )

    @staticmethod
    def _parse_support_emails(emails_str: str) -> list[str]:
        """Parse comma-separated email addresses.

        Args:
            emails_str: Comma-separated email addresses

        Returns:
            List of email addresses
        """
        if not emails_str:
            return []
        return [email.strip() for email in emails_str.split(",") if email.strip()]

    def _send_error_notification(
        self, context: GearContext, error_filename: str
    ) -> None:
        """Send simple error notification email.

        Args:
            context: the gear execution context
            error_filename: the name of the error CSV file
        """
        if not self.__support_emails:
            log.info("Notifications not configured")
            return
        if not self.__email_source:
            log.warning("Notifications not sent: sender must be configured")
            return

        log.info(
            "Sending simple error notification for %d error(s)",
            self.__collector.error_count(),
        )
        try:
            email_client = EmailClient(
                client=create_ses_client(),
                source=self.__email_source,
            )

            subject = "[pull_directory] User Processing Errors"

            # Format category breakdown
            category_breakdown = "\n".join(
                f"  {category}: {count}"
                for category, count in self.__collector.count_by_category().items()
            )

            error_count = self.__collector.error_count()
            affected_users = len(self.__collector.get_affected_users())
            dest_type = context.config.destination["type"]
            dest_id = context.config.destination["id"]

            body = (
                f"User processing completed with {error_count} errors.\n"
                "\n"
                f"Error details have been saved to: {error_filename}\n"
                "\n"
                f"Location: {dest_type} {dest_id}\n"
                "\n"
                "To access the error file:\n"
                "1. Navigate to the project in Flywheel\n"
                f"2. Look for the file: {error_filename}\n"
                "3. Download and review the errors in a spreadsheet application\n"
                "\n"
                f"Affected users: {affected_users}\n"
                "\n"
                "Error breakdown by category:\n"
                f"{category_breakdown}\n"
            )

            message_id = email_client.send_raw(
                destinations=self.__support_emails,
                subject=subject,
                body=body,
            )
            if message_id:
                log.info(
                    "Successfully sent error notification with message ID: %s",
                    message_id,
                )
            else:
                log.warning(
                    "Failed to send error notification - no message ID returned"
                )
        except Exception as error:
            # Don't fail the gear run if notification fails
            log.error(
                "Failed to send error notification: %s",
                error,
                exc_info=True,
            )

    def run(self, context: GearContext) -> None:
        """Runs the directory pull gear.

        Args:
            context: the gear execution context
        """
        assert context, "Gear context required"
        assert self.__user_filename, "User filename required"

        if self.client.dry_run:
            log.info(
                "Would write user entries to file %s on %s %s",
                self.__user_filename,
                context.config.destination["type"],
                context.config.destination["id"],
            )
            return

        try:
            yaml_text = run(user_report=self.__user_report, collector=self.__collector)
        except RepresenterError as error:
            raise GearExecutionError(
                f"Error: can't create YAML for file{self.__user_filename}: {error}"
            ) from error

        with context.open_output(
            self.__user_filename, mode="w", encoding="utf-8"
        ) as out_file:
            out_file.write(yaml_text)

        if not self.__collector.has_errors():
            log.info("Directory pull completed successfully with no errors")
            return

        # Log error summary at end of run

        log.info(
            "Directory pull completed with %d errors across %d users",
            self.__collector.error_count(),
            len(self.__collector.get_affected_users()),
        )
        log.info("Error breakdown by category:")
        for category, count in self.__collector.count_by_category().items():
            log.info("  %s: %d", category, count)

        # Export errors to CSV
        error_filename = "directory-pull-errors.csv"
        try:
            csv_content = export_errors_to_csv(self.__collector)
            with context.open_output(
                error_filename, mode="w", encoding="utf-8"
            ) as error_file:
                error_file.write(csv_content)
            log.info(
                "Wrote %d errors to %s",
                self.__collector.error_count(),
                error_filename,
            )
        except Exception as error:
            log.error(
                "Failed to write error CSV file: %s",
                error,
                exc_info=True,
            )

        # Send error notification
        self._send_error_notification(context, error_filename)


def main() -> None:
    """Main method for directory pull.

    Expects information needed for access to the user access report from
    the NACC directory on REDCap, and api key for flywheel. These must
    be given as environment variables.
    """

    GearEngine.create_with_parameter_store().run(gear_type=DirectoryPullVisitor)


if __name__ == "__main__":
    main()
